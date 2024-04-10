# Shadertoys-dataset

This repository contains the code to download, build and update the Shadertoys dataset.
The dataset is made up from fragment shader programs published on [Shadertoy](https://www.shadertoy.com/) and annotated with additional metadata for downstream filtering.
Datasets are hosted on [Huggingface](https://huggingface.co/datasets/Vipitis/Shadertoys). (maybe we name it Shadertoys-2 to avoid overwriting anything)

The main use case for this dataset is various evaluation benchmarks for (code-) language models. It can also be used for fine tuning objectives. The train/test split is shared across all subsets, however deduplication is not guaranteed, therefore data contaimination is very likely.

This project is not affiliated with Shadertoy.

## To-Dos
This project is still in progress, all datasets currently published will see a major refactor.
- [ ] pin and branch/archive Return Completion (shadereval-1) test set
- [ ] dynamically split train/test based on shaderID hash
- [~] public repository for builder scripts
- [ ] (self-)publish TaCoS 2023 paper. 
- [ ] redo structure
- [~] add thumbnails (text2img?)
- [ ] improved license detecting and tagging using `scan-code` 
- [ ] **potentially** webscraping and tagging sources/unlisted? -> current RFC: https://github.com/pygfx/shadertoy/pull/27


## Related work
* [shaders21k](https://mbaradad.github.io/shaders21k/) also sources shader programs from Shadertoy.com, however it provides rendered frames for visual representation learning. It's publication 
* [The-Stack](https://huggingface.co/datasets/bigcode/the-stack) has a `GLSL` subset. This data is sourced from GitHub.
* [The-Stack-v2](https://huggingface.co/datasets/bigcode/the-stack-v2) sources data from a larger archive. 

## Requirements
### Setup

To access shader programs that are published for `public+api` a Shadertoy account and API key is required. [Request a key](https://www.shadertoy.com/howto#q2) and setup a `SHADERTOY_KEY` environment variable.

### Dependencies

* For parsing shaders [tree-sitter-glsl](https://github.com/tree-sitter-grammars/tree-sitter-glsl) is used.

* For license detection [scancode-toolkit](https://github.com/nexB/scancode-toolkit) is used.

* For testing shaders [wgpu-shadertoy](https://github.com/pygfx/shadertoy) is used.


## License note
The contents of this repository (builder scripts, metadata) are distributed under the [Apache 2.0 license](./LICENSE). However the contents of the dataset itself are under their respective license. We do our best to annotate licenses to allow for filtering. Please see the field `license` in the dataset. Some metadata (including licenses) might be out of date, therefore we recommend checking the source