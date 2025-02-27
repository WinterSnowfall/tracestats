# tracestats

A very basic and currently horribly inefficient apitrace trace parser (covering d3d8 to d3d11) and API call stats exporter.

### How to use

Run the following command and it will explain itself:

```
python3 tracestats.py -h
```

In short, you will need to specify at least one path to a tracefile for processing (multiple paths are also accepted), e.g.:

```
python3 tracestats.py -t ~/a.trace b.trace /full/path/to/c.trace
```

Optionally, you can also specify:
- `-o /path/to/filename.json`, to use a custom output path and file name. Default behavior is to create a `.json` file in the current path using the trace name, or a `tracestats.json` file if multiple traces are specified.
- `-a /path/to/apitrace`, to specify the path to the apitrace binary. Default behavior is to try and use the $PATH apitrace, if present.

### What about other stats?

As I said, it's a very simple exporter for now, but it *may* be expanded to capture more stats at some point.

