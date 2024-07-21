from wgpu_shadertoy import Shadertoy

# shadertoy source: https://www.shadertoy.com/view/4tGGzd by koiava 
# this is on API but doesn't run or error. the window shows up and is gone.
# it gets all the way to create_render_pipeline and reaches the proxy function with PipelineDescriptor or something and then dies. I got to step carefully (enable proxy breakpoint after reaching _finish_renderpass) and look at the exact struct we try.


image_code = """
#define PIXEL_SAMPLES 		2			//Increase for higher quality
#define LIGHT_SAMPLES		2			//Increase for higher quality

#define GAMMA 				2.2			//
#define SHADOWS
#define LIGHT_CLIPPING
#define STRATIFIED_SAMPLING
const vec3 backgroundColor = vec3( 0.0 );

#define SAMPLE_TOTAL_AREA			0
#define SAMPLE_SPHERICAL_TRIANGLE	1
#define SAMPLE_NONE					2
int samplingTechnique;

//used macros and constants
#define PI 					3.1415926
#define TWO_PI 				6.2831852
#define FOUR_PI 			12.566370
#define INV_PI 				0.3183099 
#define INV_TWO_PI 			0.1591549
#define INV_FOUR_PI 		0.0795775
#define EPSILON 			0.0001 
#define EQUAL_FLT(a,b,eps)	(((a)>((b)-(eps))) && ((a)<((b)+(eps))))
#define IS_ZERO(a) 			EQUAL_FLT(a,0.0,EPSILON)
//********************************************

// random number generator **********
// from iq :)
float seed;	//seed initialized in main
float rnd() { return fract(sin(seed++)*43758.5453123); }
//***********************************

//////////////////////////////////////////////////////////////////////////
// Converting PDF from Solid angle to Area
float PdfWtoA( float aPdfW, float aDist2, float aCosThere ){
    if( aDist2 < EPSILON )
        return 0.0;
    return aPdfW * abs(aCosThere) / aDist2;
}

// Converting PDF between from Area to Solid angle
float PdfAtoW( float aPdfA, float aDist2, float aCosThere ){
    float absCosTheta = abs(aCosThere);
    if( absCosTheta < EPSILON )
        return 0.0;
    
    return aPdfA * aDist2 / absCosTheta;
}
//////////////////////////////////////////////////////////////////////////

vec3 toVec3( vec4 v ) {
    if( IS_ZERO( v.w ) ) {
        return v.xyz;
    }
    
    return v.xyz*(1.0/v.w);
}

vec3 sphericalToCartesian(	in float rho,
                          	in float phi,
                          	in float theta ) {
    float sinTheta = sin(theta);
    return vec3( sinTheta*cos(phi), sinTheta*sin(phi), cos(theta) )*rho;
}

void cartesianToSpherical( 	in vec3 xyz,
                         	out float rho,
                          	out float phi,
                          	out float theta ) {
    rho = sqrt((xyz.x * xyz.x) + (xyz.y * xyz.y) + (xyz.z * xyz.z));
    phi = asin(xyz.y / rho);
	theta = atan( xyz.z, xyz.x );
}

mat3 mat3Inverse( in mat3 m ) {
    return mat3(	vec3( m[0][0], m[1][0], m[2][0] ),
					vec3( m[0][1], m[1][1], m[2][1] ),
                    vec3( m[0][2], m[1][2], m[2][2] ) );
}

//fast inverse for orthogonal matrices
mat4 mat4Inverse( in mat4 m ) {
    mat3 rotate_inv = mat3(	vec3( m[0][0], m[1][0], m[2][0] ),
                          	vec3( m[0][1], m[1][1], m[2][1] ),
                          	vec3( m[0][2], m[1][2], m[2][2] ) );
    
    return mat4(	vec4( rotate_inv[0], 0.0 ),
                	vec4( rotate_inv[1], 0.0 ),
                	vec4( rotate_inv[2], 0.0 ),
              		vec4( (-rotate_inv)*m[3].xyz, 1.0 ) );
}
    

      
struct SurfaceHitInfo {
    vec3 position_;
	vec3 normal_;
    vec3 tangent_;
    vec2 uv_;
    int material_id_;
};


#define MTL_LIGHT 		0
#define MTL_DIFFUSE		1
    

#define OBJ_PLANE		0
#define OBJ_SPHERE		1
#define OBJ_CYLINDER	2
#define OBJ_AABB		3
#define OBJ_TRIANGLE	4
    
struct Object {
    int type_;
    int mtl_id_;
    mat4 transform_;
    mat4 transform_inv_;
    
    float params_[6];
};
    
struct Ray { vec3 origin; vec3 dir; };
struct Camera {
    mat3 rotate;
    vec3 pos;
    float fovV;
};
    
// ************ SCENE ***************
Object objects[7];
Camera camera;
//***********************************
void createAABB( mat4 transform, vec3 bound_min, vec3 bound_max, int mtl, out Object obj) {
    vec3 xAcis = normalize( vec3( 0.9, 0.0, 0.2 ) );
    vec3 yAcis = vec3( 0.0, 1.0, 0.0 );
    obj.type_ = OBJ_AABB;
    obj.mtl_id_ = mtl;
    obj.transform_ = transform;
    obj.transform_inv_ = mat4Inverse( obj.transform_ );
    obj.params_[0] = bound_min.x;
    obj.params_[1] = bound_min.y;
    obj.params_[2] = bound_min.z;
    obj.params_[3] = bound_max.x;
    obj.params_[4] = bound_max.y;
    obj.params_[5] = bound_max.z;
}

void createPlane(mat4 transform, float minX, float minY, float maxX, float maxY, int mtl, out Object obj) {
    obj.type_ = OBJ_PLANE;
    obj.mtl_id_ = mtl;
    obj.transform_ = transform;
    obj.transform_inv_ = mat4Inverse( obj.transform_ );
    obj.params_[0] = minX;			//radius
    obj.params_[1] = minY;			//min z
    obj.params_[2] = maxX;			//max z
    obj.params_[3] = maxY;			//max phi
    obj.params_[4] = 0.0;		//not used
    obj.params_[5] = 0.0;		//not used
}

void createTriangle(mat4 transform, vec2 v1, vec2 v2, vec2 v3, int mtl, out Object obj) {
    obj.type_ = OBJ_TRIANGLE;
    obj.mtl_id_ = mtl;
    obj.transform_ = transform;
    obj.transform_inv_ = mat4Inverse( obj.transform_ );
    obj.params_[0] = v1.x;			
    obj.params_[1] = v1.y;			
    obj.params_[2] = v2.x;			
    obj.params_[3] = v2.y;			
    obj.params_[4] = v3.x;		
    obj.params_[5] = v3.y;		
}

void createSphere(mat4 transform, float r, int mtl, out Object obj) {
    obj.type_ = OBJ_SPHERE;
    obj.mtl_id_ = mtl;
    obj.transform_ = transform;
    obj.transform_inv_ = mat4Inverse( obj.transform_ );
    obj.params_[0] = r;			//radius
    obj.params_[1] = r*r;		//radius^2
    obj.params_[2] = 0.0;		//not used
    obj.params_[3] = 0.0;		//not used
    obj.params_[4] = 0.0;		//not used 
    obj.params_[5] = 0.0;		//not used
}

void createCylinder(mat4 transform, float r, float minZ, float maxZ, float maxTheta, int mtl, out Object obj) {
    obj.type_ = OBJ_CYLINDER;
    obj.mtl_id_ = mtl;
    obj.transform_ = transform;
    obj.transform_inv_ = mat4Inverse( obj.transform_ );
    obj.params_[0] = r;			//radius
    obj.params_[1] = minZ;		//min z
    obj.params_[2] = maxZ;		//max z
    obj.params_[3] = maxTheta;	//max phi
    obj.params_[4] = 0.0;		//not used
    obj.params_[5] = 0.0;		//not used
}

mat4 createCS(vec3 p, vec3 z, vec3 x) {
    z = normalize(z);
    vec3 y = normalize(cross(z,x));
    x = cross(y,z);
    
    return mat4(	vec4( x, 0.0 ), 
    			 	vec4( y, 0.0 ),
    				vec4( z, 0.0 ),
    				vec4( p, 1.0 ));
}

void initScene() {
    float time = iTime;
    
    //init lights
    float r = 0.1;
    
    float xFactor = (iMouse.x==0.0)?0.0:2.0*(iMouse.x/iResolution.x) - 1.0;
    float yFactor = (iMouse.y==0.0)?0.0:2.0*(iMouse.y/iResolution.y) - 1.0;
    float x = 0.0;
    float z = -3.0-yFactor*5.0;
    float a = -1.8+sin(time*0.23);
    mat4 trans = createCS(	vec3(x, 3.0, z),
                          	vec3(0.0, sin(a), cos(a)),
                  			vec3(1.0, 0.0, 0.0));
    vec2 v1 = vec2(-2.0, -2.0);
    vec2 v2 = vec2(0.0, 2.0);
    vec2 v3 = vec2(2.0, -2.0);
    createTriangle(trans, v1, v2, v3, MTL_LIGHT, objects[0]);
    //createCylinder(trans, 0.1, 0.0, 7.0, TWO_PI, MTL_LIGHT, objects[0]);
    
    
    //plane 1
    trans = mat4(	vec4( 1.0, 0.0, 0.0, 0.0 ),
                    vec4( 0.0, 1.0, 0.0, 0.0 ),
                    vec4( 0.0, 0.0, 1.0, 0.0 ),
                    vec4( 0.0, 5.0, -10.0, 1.0 ));
    createPlane(trans, -10.0, -2.0, 10.0, 4.0, MTL_DIFFUSE, objects[1]);
   
    //plane 2
    trans = mat4(	vec4( 1.0, 0.0, 0.0, 0.0 ),
                    vec4( 0.0, 0.0, -1.0, 0.0 ),
                    vec4( 0.0, -1.0, 0.0, 0.0 ),
                    vec4( 0.0, -1.0, -4.0, 1.0 ));
    createPlane(trans, -10.0, -4.0, 10.0, 2.0, MTL_DIFFUSE, objects[2]);
 
    //Cylinder
    trans = mat4(	vec4( 0.0, 1.0, 0.0, 0.0 ),
                    vec4( 0.0, 0.0, 1.0, 0.0 ),
                    vec4( 1.0, 0.0, 0.0, 0.0 ),
                    vec4( -0.0, 3.0, -6.0, 1.0 ));
    createCylinder(trans, 4.0, -10.0, 10.0, PI/2.0, MTL_DIFFUSE, objects[3] );
    
    //sphere 1
    trans = mat4( 	vec4( 1.0, 0.0, 0.0, 0.0 ),
                    vec4( 0.0, 1.0, 0.0, 0.0 ),
                    vec4( 0.0, 0.0, 1.0, 0.0 ),
                    vec4( 2.5, 0.0, -2.0, 1.0 ));

    createSphere(trans, 1.0, MTL_DIFFUSE, objects[4] );
    
    //sphere 2
    trans = mat4( 	vec4( 1.0, 0.0, 0.0, 0.0 ),
                    vec4( 0.0, 1.0, 0.0, 0.0 ),
                    vec4( 0.0, 0.0, 1.0, 0.0 ),
                    vec4( -1.0, 0.0, -5.0, 1.0 ));

    createSphere(trans, 1.0, MTL_DIFFUSE, objects[5] );
    
    //box
    trans = createCS(	vec3(-1.5, -1.0, -3.0),
                     	vec3(0.0, 1.0, 0.0),
                     	vec3(0.2, 0.0, -0.7));
    createAABB( trans, -vec3(0.5, 0.5, 0.0), vec3(0.5, 0.5, 2.5), MTL_DIFFUSE, objects[6]);
}

// ************************  INTERSECTION FUNCTIONS **************************
bool solveQuadratic(float A, float B, float C, out float t0, out float t1) {
	float discrim = B*B-4.0*A*C;
    
	if ( discrim <= 0.0 )
        return false;
    
	float rootDiscrim = sqrt( discrim );
    
    float t_0 = (-B-rootDiscrim)/(2.0*A);
    float t_1 = (-B+rootDiscrim)/(2.0*A);
    
    t0 = min( t_0, t_1 );
    t1 = max( t_0, t_1 );
    
	return true;
}

bool rayAABBIntersection( in Ray ray, float minX, float minY, float minZ, float maxX, float maxY, float maxZ, in bool forShadowTest, out float t, out SurfaceHitInfo isect ) {
    vec3 boxMin = vec3( minX, minY, minZ );
    vec3 boxMax = vec3( maxX, maxY, maxZ );
    
    vec3 OMIN = ( boxMin - ray.origin ) / ray.dir;
    vec3 OMAX = ( boxMax - ray.origin ) / ray.dir;
    vec3 MAX = max ( OMAX, OMIN );
    vec3 MIN = min ( OMAX, OMIN );
    float t1 = min ( MAX.x, min ( MAX.y, MAX.z ) );
    t = max ( max ( MIN.x, 0.0 ), max ( MIN.y, MIN.z ) );
    
    if ( t1 <= t )
        return false;
    
    if( !forShadowTest ) {
        isect.position_ = ray.origin + ray.dir*t;
        
        if( EQUAL_FLT( isect.position_.x, minX, EPSILON ) ) {
            isect.normal_ =  vec3( -1.0, 0.0, 0.0 );
            isect.tangent_ 		= vec3( 0.0, 1.0, 0.0 );
            isect.uv_.x = (isect.position_.z - minZ)/(maxZ - minZ);
    		isect.uv_.y = (isect.position_.y - minY)/(maxY - minY);
        } else if( EQUAL_FLT( isect.position_.x, maxX, EPSILON ) ) {
            isect.normal_ =  vec3( 1.0, 0.0, 0.0 );
            isect.tangent_ = vec3( 0.0, 1.0, 0.0 );
            isect.uv_.x = (isect.position_.z - minZ)/(maxZ - minZ);
    		isect.uv_.y = (isect.position_.y - minY)/(maxY - minY);
        } else if( EQUAL_FLT( isect.position_.y, minY, EPSILON ) ) {
            isect.normal_ =  vec3( 0.0, -1.0, 0.0 );
            isect.tangent_ = vec3( 1.0, 0.0, 0.0 );
            isect.uv_.x = (isect.position_.x - minX)/(maxX - minX);
    		isect.uv_.y = (isect.position_.z - minZ)/(maxZ - minZ);
        } else if( EQUAL_FLT( isect.position_.y, maxY, EPSILON ) ) {
            isect.normal_ =  vec3( 0.0, 1.0, 0.0 );
            isect.tangent_ = vec3( 1.0, 0.0, 0.0 );
            isect.uv_.x = (isect.position_.x - minX)/(maxX - minX);
    		isect.uv_.y = (isect.position_.z - minZ)/(maxZ - minZ);
        } else if( EQUAL_FLT( isect.position_.z, minZ, EPSILON ) ) {
            isect.normal_ =  vec3( 0.0, 0.0, -1.0 );
            isect.tangent_ = vec3( 1.0, 0.0, 0.0 );
            isect.uv_.x = (isect.position_.x - minX)/(maxX - minX);
    		isect.uv_.y = (isect.position_.y - minY)/(maxY - minY);
        } else if( EQUAL_FLT( isect.position_.z, maxZ, EPSILON ) ) {
            isect.normal_ =  vec3( 0.0, 0.0, 1.0 );
            isect.tangent_ = vec3( 1.0, 0.0, 0.0 );
            isect.uv_.x = (isect.position_.x - minX)/(maxX - minX);
    		isect.uv_.y = (isect.position_.y - minY)/(maxY - minY);
        }
        
        isect.uv_ /= 2.0;
    }
    
    return true;
}

bool rayIntersectsTriangle(in Ray ray, vec3 v0, vec3 v1, vec3 v2, in bool forShadowTest, out float t, out SurfaceHitInfo isect){
    vec3 p = ray.origin;
    vec3 d = ray.dir;
    
	vec3 e1,e2,h,s,q;
	float a,f,u,v;
	e1 = v1-v0;
	e2 = v2-v0;

	h = cross(d,e2);
	a = dot(e1,h);

	if (a > -0.00001 && a < 0.00001)
		return false;

	f = 1.0 / a;
	s = p-v0;
	u = f * dot(s,h);

	if (u < 0.0 || u > 1.0)
		return false;

	q = cross(s,e1);
	v = f * dot(d,q);

	if (v < 0.0 || u + v > 1.0)
		return false;

	// at this stage we can compute t to find out where
	// the intersection point is on the line
	t = f * dot(e2,q);

	//uv = vec2(u, v);
    
    if( !forShadowTest ) {
        isect.position_ = ray.origin + ray.dir*t;
        isect.normal_ =  vec3( 0.0, 0.0, 1.0 );
        isect.tangent_ 		= vec3( 1.0, 0.0, 0.0 );
        isect.uv_.x = isect.position_.x;
        isect.uv_.y = isect.position_.y;
    }
	
	if (t > 0.00001) // ray intersection
		return true;
    
	// this means that there is a line intersection
	// but not a ray intersection
	return false;
}

bool raySphereIntersection( in Ray ray, in float radiusSquared, in bool forShadowTest, out float t, out SurfaceHitInfo isect ) {
    float t0, t1;
    vec3 L = ray.origin;
    float a = dot( ray.dir, ray.dir );
    float b = 2.0 * dot( ray.dir, L );
    float c = dot( L, L ) - radiusSquared;
    
    if (!solveQuadratic( a, b, c, t0, t1))
		return false;
    
    if( t0 > 0.0 ) {
    	t = t0;
    } else {
        if ( t1 > 0.0 ) {
            t = t1;
        } else {
            return false;
        }
    }
    
    if( !forShadowTest ) {
        isect.position_ = ray.origin + ray.dir*t;
        isect.normal_ = normalize( isect.position_ );

        float rho, phi, theta;
        cartesianToSpherical( isect.normal_, rho, phi, theta );
        isect.uv_.x = phi/PI;
        isect.uv_.y = theta/TWO_PI;

        isect.tangent_ = vec3( 0.0, 1.0, 0.0 );
        vec3 tmp = cross( isect.normal_, isect.tangent_ );
        isect.tangent_ = normalize( cross( tmp, isect.normal_ ) );
    }
	
	return true;
}


bool rayAAPlaneIntersection( in Ray ray, in float min_x, in float min_y, in float max_x, in float max_y, in bool forShadowTest, out float t, out SurfaceHitInfo isect ) {
    if ( IS_ZERO( ray.dir.z ) )
    	return false;
    
    t = ( -ray.origin.z ) / ray.dir.z;
    
    isect.position_ = ray.origin + ray.dir*t;
    
    if( (isect.position_.x < min_x) ||
       	(isect.position_.x > max_x) ||
      	(isect.position_.y < min_y) ||
      	(isect.position_.y > max_y) )
        return false;
    
    if( !forShadowTest ) {
        isect.uv_.x 		= (isect.position_.x - min_x)/(max_x - min_x);
        isect.uv_.y 		= (isect.position_.y - min_y)/(max_y - min_y);
        isect.normal_ 		= vec3( 0.0, 0.0, 1.0 );
        isect.tangent_ 		= vec3( 1.0, 0.0, 0.0 );
    }
    
    return true;
}

bool rayCylinderIntersection( in Ray r, in float radius, in float minZ, in float maxZ, in float maxPhi, in bool forShadowTest, out float t, out SurfaceHitInfo isect ) {
	float phi;
	vec3 phit;
    
	// Compute quadratic cylinder coefficients
	float a = r.dir.x*r.dir.x + r.dir.y*r.dir.y;
	float b = 2.0 * (r.dir.x*r.origin.x + r.dir.y*r.origin.y);
	float c = r.origin.x*r.origin.x + r.origin.y*r.origin.y - radius*radius;
 
	// Solve quadratic equation for _t_ values
	float t0, t1;
	if (!solveQuadratic( a, b, c, t0, t1))
		return false;

    if ( t1 < 0.0 )
        return false;
    
	t = t0;
    
	if (t0 < 0.0)
		t = t1;

	// Compute cylinder hit point and $\phi$
	phit = r.origin + r.dir*t;
	phi = atan(phit.y,phit.x);
    phi += PI;
    
	if (phi < 0.0)
        phi += TWO_PI;
 
	// Test cylinder intersection against clipping parameters
	if ( (phit.z < minZ) || (phit.z > maxZ) || (phi > maxPhi) ) {
		if (t == t1)
            return false;
		t = t1;
		// Compute cylinder hit point and $\phi$
		phit = r.origin + r.dir*t;
		phi = atan(phit.y,phit.x);
        phi += PI;

		if ( (phit.z < minZ) || (phit.z > maxZ) || (phi > maxPhi) )
			return false;
	}
    
    if( !forShadowTest ) {
        isect.position_ = phit;
        isect.uv_.x = (phit.z - minZ)/(maxZ - minZ);
        isect.uv_.y = phi/maxPhi;
        isect.normal_ = normalize( vec3( phit.xy, 0.0 ) );
        isect.tangent_ = vec3( 0.0, 0.0, 1.0 );
    }
    
	return true;
}

bool rayObjectIntersect( in Ray ray, in Object obj, in float distMin, in float distMax, in bool forShadowTest, out SurfaceHitInfo hit, out float dist ) {
    bool hitResult = false;
    float t;
    SurfaceHitInfo currentHit;

    //Convert ray to object space
    Ray rayLocal;
    rayLocal.origin = toVec3( obj.transform_inv_*vec4( ray.origin, 1.0 ) );
    rayLocal.dir 	= toVec3( obj.transform_inv_*vec4( ray.dir   , 0.0 ) );

    if( obj.type_ == OBJ_PLANE ) {
        hitResult = rayAAPlaneIntersection( rayLocal, obj.params_[0], obj.params_[1], obj.params_[2], obj.params_[3], forShadowTest, t, currentHit );
    } else if( obj.type_ == OBJ_SPHERE ) {
        hitResult = raySphereIntersection( 	rayLocal, obj.params_[1], forShadowTest, t, currentHit );
    } else if( obj.type_ == OBJ_CYLINDER ) {
        hitResult = rayCylinderIntersection(rayLocal, obj.params_[0], obj.params_[1], obj.params_[2], obj.params_[3], forShadowTest, t, currentHit );
    } else if( obj.type_ == OBJ_AABB ) {
        hitResult = rayAABBIntersection( rayLocal, obj.params_[0], obj.params_[1], obj.params_[2], obj.params_[3], obj.params_[4], obj.params_[5], forShadowTest, t, currentHit );
    } else if( obj.type_ == OBJ_TRIANGLE ) {
        vec3 v1 = vec3(obj.params_[0], obj.params_[1], 0.0);
        vec3 v2 = vec3(obj.params_[2], obj.params_[3], 0.0);
        vec3 v3 = vec3(obj.params_[4], obj.params_[5], 0.0);
        hitResult = rayIntersectsTriangle(rayLocal, v1, v2, v3, forShadowTest, t, currentHit);
    }

    if( hitResult && ( t > distMin ) && ( t < distMax ) ) {
        //Convert results to world space
        currentHit.position_ = toVec3( obj.transform_*vec4( currentHit.position_, 1.0 ) );
        currentHit.normal_   = toVec3( obj.transform_*vec4( currentHit.normal_  , 0.0 ) );
        currentHit.tangent_  = toVec3( obj.transform_*vec4( currentHit.tangent_ , 0.0 ) );

        dist = t;
        hit = currentHit;
        hit.material_id_ = obj.mtl_id_;
        return true;
    }
    
    return false;
}

#define CHECK_OBJ( obj ) { SurfaceHitInfo currentHit; float currDist; if( rayObjectIntersect( ray, obj, distMin, nearestDist, forShadowTest, currentHit, currDist ) && ( currDist < nearestDist ) ) { nearestDist = currDist; hit = currentHit; } }
bool raySceneIntersection( in Ray ray, in float distMin, in bool forShadowTest, out SurfaceHitInfo hit, out float nearestDist ) {
    nearestDist = 10000.0;
    CHECK_OBJ( objects[0] );
    if(!forShadowTest) {	//Hack optimization for shadow rays
        CHECK_OBJ( objects[1] );
        CHECK_OBJ( objects[2] );
        CHECK_OBJ( objects[3] );
    }
    CHECK_OBJ( objects[4] );
    CHECK_OBJ( objects[5] );
    CHECK_OBJ( objects[6] );
    return ( nearestDist < 1000.0 );
}
// ***************************************************************************

 
// Geometry functions ***********************************************************
vec2 uniformPointWithinCircle( in float radius, in float Xi1, in float Xi2 ) {
    float r = radius*sqrt(Xi1);
    float theta = Xi2*TWO_PI;
	return vec2( r*cos(theta), r*sin(theta) );
}

vec3 uniformPointWitinTriangle( in vec3 v1, in vec3 v2, in vec3 v3, in float Xi1, in float Xi2 ) {
    Xi1 = sqrt(Xi1);
    return (1.0-Xi1)*v1 + Xi1*(1.0-Xi2)*v2 + Xi1*Xi2*v3;
}

vec3 uniformDirectionWithinCone( in vec3 d, in float phi, in float sina, in float cosa ) {    
	vec3 w = normalize(d);
    vec3 u = normalize(cross(w.yzx, w));
    vec3 v = cross(w, u);
	return (u*cos(phi) + v*sin(phi)) * sina + w * cosa;
}

vec3 localToWorld( in vec3 localDir, in vec3 normal )
{
    vec3 binormal = normalize( ( abs(normal.x) > abs(normal.z) )?vec3( -normal.y, normal.x, 0.0 ):vec3( 0.0, -normal.z, normal.y ) );
	vec3 tangent = cross( binormal, normal );
    
	return localDir.x*tangent + localDir.y*binormal + localDir.z*normal;
}

vec3 sampleHemisphereCosWeighted( in vec3 n, in float Xi1, in float Xi2 ) {
    float theta = acos(sqrt(1.0-Xi1));
    float phi = TWO_PI * Xi2;

    return localToWorld( sphericalToCartesian( 1.0, phi, theta ), n );
}

vec3 randomHemisphereDirection( const vec3 n, in float Xi1, in float Xi2 ) {
    vec2 r = vec2(Xi1,Xi2)*TWO_PI;
	vec3 dr=vec3(sin(r.x)*vec2(sin(r.y),cos(r.y)),cos(r.x));
	return dot(dr,n) * dr;
}

vec3 randomDirection( in float Xi1, in float Xi2 ) {
    float theta = acos(1.0 - 2.0*Xi1);
    float phi = TWO_PI * Xi2;
    
    return sphericalToCartesian( 1.0, phi, theta );
}

///////////////////////////////////////////////////////////////////////
void initCamera( 	in vec3 pos,
                	in vec3 target,
                	in vec3 upDir,
                	in float fovV
               ) {
	vec3 back = normalize( pos-target );
	vec3 right = normalize( cross( upDir, back ) );
	vec3 up = cross( back, right );
    camera.rotate[0] = right;
    camera.rotate[1] = up;
    camera.rotate[2] = back;
    camera.fovV = fovV;
    camera.pos = pos;
}

void updateCamera( int strata ) {
    float strataSize = 1.0/float(PIXEL_SAMPLES);
    float r1 = strataSize*(float(strata)+rnd());
    //update camera pos
    float cameraZ = 4.0;
    vec3 upDir = vec3( 0.0, 1.0, 0.0 );
    vec3 pos1, pos2;
    pos1 = vec3( sin(iTime*0.154)*2.0, 2.0 + sin(iTime*0.3)*2.0, cameraZ + sin(iTime*0.8) );

    camera.pos = pos1;
    
    vec3 target = vec3( sin(iTime*0.4)*0.3, 1.0, -5.0 );
    
	vec3 back = normalize( camera.pos-target );
	vec3 right = normalize( cross( upDir, back ) );
	vec3 up = cross( back, right );
    camera.rotate[0] = right;
    camera.rotate[1] = up;
    camera.rotate[2] = back;
}

Ray genRay( in vec2 pixel, in float Xi1, in float Xi2 ) {
    Ray ray;
	vec2 iPlaneSize=2.*tan(0.5*camera.fovV)*vec2(iResolution.x/iResolution.y,1.);
	vec2 ixy=(pixel/iResolution.xy - 0.5)*iPlaneSize;
    ray.origin = camera.pos;
    ray.dir = camera.rotate*normalize(vec3(ixy.x,ixy.y,-1.0));
	return ray;
}

bool intersectPlane(vec3 plane_n, vec3 plane_p, vec3 ray_o, vec3 ray_d, out float t) { 
    // assuming vectors are all normalized
    float denom = dot(plane_n, ray_d); 
    if (abs(denom) > 1e-7) { 
        vec3 vec = plane_p - ray_o; 
        t = dot(vec, plane_n) / denom; 
        return (t >= 0.0); 
    } 
 
    return false; 
}

vec2 angular_to_cartesian(float phi) {
    return vec2(cos(phi), sin(phi));
}

float cartesian_to_angular(vec2 w) {
	return atan(float(-w.y), float(-w.x)) + PI;
}

//Gram-Schmidt method
vec3 orthogonalize(in vec3 a, in vec3 b) {
    //we assume that a is normalized
	return normalize(b - dot(a,b)*a);
}

vec3 slerp(vec3 start, vec3 end, float percent)
{
	// Dot product - the cosine of the angle between 2 vectors.
	float cosTheta = dot(start, end);
	// Clamp it to be in the range of Acos()
	// This may be unnecessary, but floating point
	// precision can be a fickle mistress.
	cosTheta = clamp(cosTheta, -1.0, 1.0);
	// Acos(dot) returns the angle between start and end,
	// And multiplying that by percent returns the angle between
	// start and the final result.
	float theta = acos(cosTheta)*percent;
	vec3 RelativeVec = normalize(end - start*cosTheta);
     // Orthonormal basis
								 // The final result.
	return ((start*cos(theta)) + (RelativeVec*sin(theta)));
}

//Function which does triangle sampling proportional to their solid angle.
//You can find more information and pseudocode here:
// * Stratified Sampling of Spherical Triangles. J Arvo - ‎1995
// * Stratified sampling of 2d manifolds. J Arvo - ‎2001
void sampleSphericalTriangle(in vec3 A, in vec3 B, in vec3 C, in float Xi1, in float Xi2, out vec3 w, out float wPdf) {
	
    vec3 v0 = B - A;
    vec3 v1 = C - A;
    vec3 v2 = cross(v0, v1);
    float a = length(v2);
    float alpha = acos(dot(v0, v1) / (a * length(v0)));
    float beta = acos(dot(v1, v2) / (a * length(v1)));
    float gamma = acos(dot(v2, v0) / (a * length(v2)));
    float s = sin(alpha);
    float c = cos(alpha);
    float t = sin(beta);
    float u = cos(beta);
    float p = sin(gamma);
    float q = cos(gamma);
    float r = sqrt(Xi1);
    float sigma = sqrt(Xi2);
    float z = r * c * t;
    float x = r * s * p;
    float y = r * s * q;
    w = vec3(x, y, z);
    wPdf = (a * sigma * s) / (4.0 * PI);
}

void sampleDirectLight( vec3 pos,
                       	vec3 normal,
                        float Xi1,
                        float Xi2, 
                       	out vec3 dir,
                       	out float pdf ) {
    float height = objects[0].params_[2] - objects[0].params_[1];
    float r = objects[0].params_[0];
    float pdfA;
    float d2;
    float aCosThere;
    float theta;
    float thetaPdf;
    float h;
    float hPdf;
    
    //convert position to object space
    pos = toVec3( objects[0].transform_inv_*vec4(pos, 1.0) );
    normal = toVec3( objects[0].transform_inv_*vec4(normal, 0.0) );
    
    vec3 v1 = vec3(objects[0].params_[0], objects[0].params_[1], 0.0);
    vec3 v2 = vec3(objects[0].params_[2], objects[0].params_[3], 0.0);
    vec3 v3 = vec3(objects[0].params_[4], objects[0].params_[5], 0.0);
    vec3 n = vec3(0.0, 0.0, 1.0);
    
    if(samplingTechnique == SAMPLE_TOTAL_AREA){
        vec3 p = uniformPointWitinTriangle( v1, v2, v3, Xi1, Xi2 );
        float triangleArea = length(cross(v1-v2,v3-v2)) * 0.5;
        pdfA = 1.0/triangleArea;
        
        dir = p - pos;
        d2 = dot(dir,dir);
        dir /= sqrt(d2);
        aCosThere = max(0.0,dot(-dir,n));
        pdf = PdfAtoW( pdfA, d2, aCosThere );
    } else {
        vec3 A = normalize(v1 - pos);
        vec3 B = normalize(v2 - pos);
        vec3 C = normalize(v3 - pos);
        sampleSphericalTriangle(A, B, C, Xi1, Xi2, dir, pdf);
        if(dot(-dir,n) < 0.0){
            pdf = 0.0;
        }
    }
    
    //convert dir to world space
    dir = toVec3( objects[0].transform_*vec4(dir,0.0) );
}

bool isLightVisible( Ray shadowRay ) {
    float distToHit;
    SurfaceHitInfo tmpHit;
    
    raySceneIntersection( shadowRay, EPSILON, true, tmpHit, distToHit );
    
    return ( tmpHit.material_id_ == MTL_LIGHT );
}


vec3 Radiance( in Ray ray, float Xi ) {
    vec3 L = vec3(4.0);
    vec3 Lo = vec3( 0.0 );
    
    vec3 Wo = ray.dir*(-1.0);
    SurfaceHitInfo hit;
    float dist = 1000.0;

    if( raySceneIntersection( ray, 0.0, false, hit, dist ) ) {
        if( hit.material_id_ == MTL_LIGHT ) {
            Lo = (dot(hit.normal_, Wo) > 0.0)? L : vec3(0.0, 0.0, 0.0);
        } else {
            for(int i=0; i<LIGHT_SAMPLES; i++){
                vec3 Wi;
                float pdfWi;
                vec3 n = hit.normal_ * ((dot(hit.normal_, Wo) > 0.0 )? 1.0 : -1.0);
                
            	float Xi1 = rnd();
            	float Xi2 = rnd();
#ifdef STRATIFIED_SAMPLING
                float strataSize = 1.0 / float(LIGHT_SAMPLES);
                Xi2 = strataSize * (float(i) + Xi2);
#endif
                
                sampleDirectLight( hit.position_, n, Xi1, Xi2, Wi, pdfWi );
                float dotNWi = dot( Wi, n );

                if ( (pdfWi > EPSILON) && (dotNWi > 0.0) ) {
                    bool visible = true;
#ifdef SHADOWS
                    Ray shadowRay = Ray( hit.position_ + n*EPSILON, Wi );
                    if ( !isLightVisible( shadowRay ) ) {
                        visible = false;
                    }
#endif
                    if(visible) {
                        float brdf_pdf;

                        vec3 brdf = vec3(1.0/PI);//max(0.0, dot(Wi, hit.normal_))*vec3(1.0);//Material_Evaluate( hit, Wo, Wi );
						vec3 Li = L/pdfWi;
                        Lo += (brdf*Li*abs(dotNWi));
                    }
                }
            }
            Lo *= 1.0/float(LIGHT_SAMPLES);
            
        }
    }
        
    return Lo;
}

void initSamplingTechnique(float p) {
    float split = iMouse.x;
    split = (split == 0.0)? iResolution.x * 0.5 : split;
    float k = iMouse.x/iResolution.x;
    float split1 = iMouse.x*k;
    float split2 = iMouse.x + (iResolution.x-iMouse.x)*k;
    
    if(p < split-1.0) {
        samplingTechnique = SAMPLE_TOTAL_AREA;
    } else if(p > split+1.0){
        samplingTechnique = SAMPLE_SPHERICAL_TRIANGLE;
    } else {
        samplingTechnique = SAMPLE_NONE;
    }
}

void mainImage( out vec4 fragColor, in vec2 fragCoord )
{
    seed = /*iTime +*/ iResolution.y * fragCoord.x / iResolution.x + fragCoord.y / iResolution.y;
    initSamplingTechnique(fragCoord.x);

    if(samplingTechnique == SAMPLE_NONE) {
        fragColor = vec4( 1.0 );
    } else {
        float fov = radians(45.0);
        initCamera( vec3( 0.0, 0.0, 0.0 ),
                    vec3( 0.0, 0.0, 0.0 ),
                    vec3( 0.0, 1.0, 0.0 ),
                    fov
                    );

        initScene();

        vec3 accumulatedColor = vec3( 0.0 );
        float oneOverSPP = 1.0/float(PIXEL_SAMPLES);
        float strataSize = oneOverSPP;
        Ray ray;

        for( int si=0; si<PIXEL_SAMPLES; ++si ){
            updateCamera( si );

            vec2 screenCoord = fragCoord.xy + vec2( strataSize*( float(si) + rnd() ), rnd() );
            ray = genRay( screenCoord, rnd(), rnd() );

            if( length( ray.dir ) < 0.2 ) {
                accumulatedColor = vec3( 0.0 );
            } else {
                accumulatedColor += Radiance( ray, strataSize*( float(si) + rnd() ) );
            }
        }

        //devide to sample count
        accumulatedColor = accumulatedColor*oneOverSPP;

        //gamma correction
        accumulatedColor = pow( accumulatedColor, vec3( 1.0 / GAMMA ) );


        fragColor = vec4( accumulatedColor,1.0 );
    }
}
"""


shader = Shadertoy(image_code, shader_type="glsl")

if __name__ == "__main__":
    shader.show()