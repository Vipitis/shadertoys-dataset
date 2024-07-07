# Shadertoys-dataset

This repository contains the code to download, build and update the Shadertoys dataset.
The dataset is made up from fragment shader programs published on [Shadertoy](https://www.shadertoy.com/) and annotated with additional metadata for downstream filtering.
Datasets are hosted on [Huggingface](https://huggingface.co/datasets/Vipitis/Shadertoys), (no longer public). (maybe we name it Shadertoys-2 to avoid overwriting anything)

The main use case for this dataset is various evaluation benchmarks for (code-) language models.

This project is not affiliated with Shadertoy. It makes use of the Shadertoy.com API.

## To-Dos
This project is still in progress, all datasets currently published will see a major refactor.
- [ ] pin and branch/archive Return Completion (shadereval-1) test set
- [ ] dynamically split train/test based on shaderID hash (might not do a train split)
- [~] public repository for builder scripts (you are here!)
- [ ] (self-)publish TaCoS 2023 paper. 
- [~] redo structure
- [~] add thumbnails (text2img?)
- [x] improved license detecting and tagging using `scan-code` 
- [ ] **potentially** webscraping and tagging sources/unlisted? -> current RFC: https://github.com/pygfx/shadertoy/pull/27


## Related work
* [shaders21k](https://mbaradad.github.io/shaders21k/) also sources shader programs from Shadertoy.com, however it provides rendered frames for visual representation learning. It is available as a alreanative to downloading from the API.
* [The-Stack](https://huggingface.co/datasets/bigcode/the-stack) has a `GLSL` subset. This data is sourced from GitHub.
* [The-Stack-v2](https://huggingface.co/datasets/bigcode/the-stack-v2) sources data from a larger archive. 

## Requirements
### Setup

To access shader programs that are published for `public+api` a Shadertoy account and API key is required. [Request a key](https://www.shadertoy.com/howto#q2) and setup a `SHADERTOY_KEY` environment variable.

If you want to use shaders20k (Shadertoy subset of [shaders21k](https://mbaradad.github.io/shaders21k/)), please download the [all_codes.zip](http://data.csail.mit.edu/synthetic_training/shaders21k/all_codes.zip) and place it to `./data/shaders20k/`.

### Dependencies

* For parsing shaders [tree-sitter-glsl](https://github.com/tree-sitter-grammars/tree-sitter-glsl) will be used.

* For license detection [scancode-toolkit](https://github.com/nexB/scancode-toolkit) is used.

* For testing shaders [wgpu-shadertoy](https://github.com/pygfx/shadertoy) is used.

* for validation we rely on [naga](https://crates.io/crates/naga-cli), please make sure the `naga` command works. We currently use version 0.19.0 due to the above dependencies, we hope to update to 0.20 soon as some of the validation failures have since been addressed.


## Usage

There is currently two out of three scripts available. Plenty of defaults are set and example files are provided in `./data/`

### Download
```shell
$>python download.py --mode full --num_shaders 100
```
will download the newest 100 shaders from Shadertoy.com via the API and save them to the `./data/raw/` directory as a .jsonl file.

To extract and translate shaders from the shaders20k dataset use:
```shell
$>python download.py --mode shaders20k
```

see `download.py --help` for more options. Or look at the [source](./download.py)

### Annotate
```shell
$>python annotate.py --mode "redo" --columns "license, functions"
```
this flattens the nested renderpasses into a single dict and adds relevant information like licenses, function indicies and test-validation. It seems to only do take a few minutes now.
alternatively the mode `update` allows to overwrite the columns of already flattened files.

### Upload (missing) /prepare
Filter and 
scripts to build train/test split and upload them to Huggingface aren't written yet.


## License note
The contents of this repository (builder scripts, metadata) are distributed under the [Apache 2.0 license](./LICENSE). However the contents of the dataset itself are under their respective license. We do our best to annotate licenses to allow for filtering. Please see the field `license` in the dataset. Some metadata (including licenses) might be out of date, therefore we recommend checking the source