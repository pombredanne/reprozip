ReproZip pack file format
=========================

The pack command creates an archive that contains the necessary files and environment information to reproduce the experiment elsewhere. Because reproducibility is the objective, it is meant to be a stable format, and should it evolve, we intend to keep the previous ones.

General structure
-----------------

Packed experiments have the .rpz extension by default. They are an (optionally gzipped) tar archive containing at least a METADATA/version file, which indicates the file format. Currently, it always contains either "`REPROZIP VERSION 1\n`" or "`REPROZIP VERSION 2\n`" (without quotes of any kind).

Format version 1
----------------

* `METADATA/trace.sqlite3` is the original trace file generated by the C tracer.
* `METADATA/config.yml` is the configuration file that the pack command processed to make this pack. It contains information about the files that were included, organized by distribution package.
* `DATA/` contains the files listed in the configuration (except packages with `packfiles: false`).

Format version 2
----------------

In this version, the outer archive is usually uncompressed, and the `DATA/` directory is placed in a separate archive named `DATA.tar.gz`. This has the added benefit or keeping the metadata uncompressed, allowing for faster access.
