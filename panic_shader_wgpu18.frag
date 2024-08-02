#version 450 core

vec4 i_mouse;
vec4 i_date;
vec3 i_resolution;
float i_time;
vec3 i_channel_resolution[4];
float i_time_delta;
int i_frame;
float i_framerate;

// Shadertoy compatibility, see we can use the same code copied from shadertoy website

#define iMouse i_mouse
#define iDate i_date
#define iResolution i_resolution
#define iTime i_time
#define iChannelResolution i_channel_resolution
#define iTimeDelta i_time_delta
#define iFrame i_frame
#define iFrameRate i_framerate

#define mainImage shader_main

float DENS = 10.;                         // target average density per cell

#define hash2(p)      fract(sin((p)*mat2(127.1,311.7, 269.5,183.3)) *43758.5453123) // https://www.shadertoy.com/view/llySRh
#define lcg(p)        toFloat( p = p * 1664525u + 1013904223u )
#define toFloat(p)  ( float(p)  / float(0xffffffffu) )
#define toUint(p)     uint( (p) * float(0xffffffffu) )

// Poisson generator via Inverse transform sampling ( for small d ) https://en.wikipedia.org/wiki/Poisson_distribution#Generating_Poisson-distributed_random_variables
float Poisson(vec2 U, float d) {          // d = target average density
    float k = exp(-d);
    float x = exp(dot(U, U) / 2.0);
    return abs(x * k / (2.0 * 3.1415926535897932384626433832795));
}
    
void mainImage( out vec4 O,  vec2 u )
{
    vec2 R = iResolution.xy,
         M = length(iMouse.xy) < 10. ? vec2(0) : 2.*iMouse.xy/R-1.,
         S = 4.*exp2(2.*M.x) / R.yy,
         U = S * ( 2.*u - R ) - iTime,
         I = floor(U), F = fract(U), P;
    
 // O = vec4( 2.-R.y/8.*length(hash2(I)-F) ); return; // test: one single value per cell

    float d = 1e5, i = 0.,
           n = Poisson(I, DENS );         // number of dot per cell = Poisson law
    for( ; i < n; i++ )                   // then, generates n Uniform dots in the cell
        P = F - hash2(I+i/100.),
        d = min(d, dot(P,P) );
                         // dot size proportional if big or 1 pixel if small 
    O = vec4( max(0., 1. - min(R.y/8.,.5/S.x)* sqrt(d) ) );   // draw points 
    O.b += .2*mod(I.x+I.y,2.);            // show cells
    O = sqrt(O);                          // to sRGB
}

layout(location = 0) in vec2 vert_uv;

struct ShadertoyInput {
    vec4 si_mouse;
    vec4 si_date;
    vec3 si_resolution;
    float si_time;
    vec3 si_channel_res[4];
    float si_time_delta;
    int si_frame;
    float si_framerate;
};

layout(binding = 0) uniform ShadertoyInput input;
out vec4 FragColor;
void main(){

    i_mouse = input.si_mouse;
    i_date = input.si_date;
    i_resolution = input.si_resolution;
    i_time = input.si_time;
    i_channel_resolution = input.si_channel_res;
    i_time_delta = input.si_time_delta;
    i_frame = input.si_frame;
    i_framerate = input.si_framerate;
    vec2 frag_uv = vec2(vert_uv.x, 1.0 - vert_uv.y);
    vec2 frag_coord = frag_uv * i_resolution.xy;

    shader_main(FragColor, frag_coord);

}
