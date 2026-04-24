# FTP Period Helper Update

The FTP Download page now has a Date and Month Helper card directly below the FTP Download header.

## What changed

- User can choose **Master data** or **Billed data** before starting the FTP job.
- For **Master data**, user selects the month from a month picker.
- For **Billed data**, user selects the FTP date from a date picker.
- Billed local month folder is also visible and editable because billed local paths use both month and date.
- Remote folder and local subfolder values are automatically filled into every DISCOM profile.
- Users can still manually edit Remote folder and Local subfolder in each FTP profile after the helper fills them.
- Default output root switches between `G:\MASTER` and `G:\BILLED` only when the output root is blank or still one of those default paths.

## Examples

Master month March 2026 fills:

```text
Remote folder: /01-MASTER_DATA/MAR_2026/
Local subfolder: MAR_2026/MVVNL
```

Billed date 24 April 2026 fills:

```text
Remote folder: /03_CSV_BILLED/24042026/
Local subfolder: MAR_2026/24042026/MVVNL
```

The existing Stop button and Skip existing files behavior remain unchanged.
