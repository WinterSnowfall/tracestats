# tracestats

A humble apitrace trace parser and API call stats exporter, covering APIs from d3d8 to d3d11, with an included web app/search engine. It collects statistical data from apitrace files, which it then exports in JSON format. The JSON files can in turn be uploaded to the included web app/search engine and queried from a consolidated database.

### How to use

Run the following command and it will explain itself:

```
python3 tracestats.py -h
```

In short, you will need to specify at least one path to a tracefile for processing (multiple paths are also accepted), e.g.:

```
python3 tracestats.py -i ~/a.trace b.trace /full/path/to/c.trace
```

Optionally, you can also specify:
- `-o /path/to/filename.json`, to use a custom output path and file name. Default behavior is to create a `.json` file in the export folder using the trace name, or a `tracestats.json` file if multiple traces are specified.
- `-n "friendly name"`, to specify a user friendly application name. Default behavior is to leave it blank.
- `-l "link"`, to specify a custom link URL. Default behavior is to use a PCGW search link based on the application name.
- `-s api_to_skip1,api_to_skip2`, to specify which APIs to skip. Useful for filtered batched processing.
- `-a /path/to/apitrace`, to specify the path to the apitrace binary. Default behavior is to try and use the $PATH apitrace, if present.

### What about some other stats which I noticed are missing?

As I said, it's a rather humble statistics exporter for now, but it *may* be expanded at some point to capture even more data.

### What's in the "django" folder?

A simple web application for uploading and querying exported tracestats JSON data, developed using Django. Note that it is provided only for reference, with the sqlite database not included (it can be generated very easily, however, using the Django manage script). For information on usage, deployment steps and so on please refer to the [Django documentation](https://docs.djangoproject.com/).

