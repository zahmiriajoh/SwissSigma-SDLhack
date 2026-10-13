# Global preferences

## Code style
- Concise and modular. Prefer small, composable functions over long ones.
- Brief but informative comments and docstrings — one line where one line suffices, not multi-line blocks.
- Reuse common code blocks; import shared helpers instead of duplicating, even across script directories.
- Keep code as simple as possible. 

## Specific code
- When writing code that reads in atomistic files (e.g. `.xyz`, `.cif`, etc.), always check that atom ordering is preserved. If it is not, find another method that preserves atom ordering. If no method can be found, raise the issue prominently and ask me to decide what to do.
- If you need to test something that requires activating a conda or mamba environment, write a bash script that runs `source ~/.bashrc` and `mamba activate (environment_name)`, and run that script, instead of trying to run the environment activation command in the terminal straightaway.

## Documentation
- Documentation needs to be kept updated and stay consistent across all the documents in the workspace.

## Figures
- Check the rendered figure: no axis tick labels (or point labels) may overlap. If they do, reduce the font size or move them.
- Use a colour-blind-friendly palette (e.g. Okabe–Ito; `cividis`/`viridis` for colour maps), never red against green. Where two categories meet in one figure, add a second cue (marker, line style or hatch).
- Maintain a consistent color palette where possible across all figures in the same project. Where there are clearly demarcated key experiments, it is fine to maintain one color palette per experiment. 
- Capitalise the first letter of the first word of any axis label or titles.

## Working style
- Ask questions rather than assume, especially when the task needs non-coding knowledge (domain science, experimental setup, project intent). Never guess at these.
- After writing new files or code, do a final sweep: can it be made more concise and readable?

## git 
- Commit for each key change, but do not push.
- In each commit, give an informative title, and then at most 2 bullet points. If there are more than 2 bullet points, break up the commit into smaller ones.

## Storage 
- Quotas on storage and number of files can lead to problems halfway through a project. Always measure roughly how many files might be created and how much storage might be needed before starting or asking me to start a large batch of calculations. 

## Do not change
- Never change anything in mounted folders, only ever read from them.
- Do not change anything in the reference folders:
    - `SwissSigma-SDLhack/data`
    - `SwissSigma-SDLhack/data/project_proposal`
