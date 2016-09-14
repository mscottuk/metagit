#Metagit-py

This is a Python tool and API which defines and queries metadata on paths in a Git repository, storing the metadata in a separate branch in Git. This is a prototype version of a tool to demonstrate this model.

A read-only version, for viewing the metadata, exists for the Mac: [metagit-mac](http://github.com/mscottuk/metagit-mac).

## About Metagit

Metagit allows metadata to be defined on paths within a Git repository.

Version control systems are used widely for tracking edits to data files, especially when working in teams with simultaneous editors. They track who made edits and when, and provide tools for comparing changes made and for resolving conflicts when the same file is edited by two people. Attaching metadata to files which stays with the data and tracking changes can be difficult if the file format does not support it. The utility and maturity of version control system tools make them a good candidate for a metadata store. 

Metagit allows recording key-value metadata for objects in a revision control system, specifically Git. We take advantage of Git's data store to permit the values to be blobs, opening up other possibilities such as defining thumbnails for files and folders.


Propagation rules, which define when metadata follows a file after modifications to the repository, are as follows:

* Metadata should reside with a single commit
* Metadata should be capable of propagating to later data commits
* Metadata should not affect previous versions of a file
* Adding metadata to an earlier data commit should not override metadata already defined on a later commit
* Metadata should not automatically carry forward on a file when its contents have been modified
* Branching does not affect metadata propagation and metadata should propagate to all branches equally
* Merging of branches should stop metadata from propagating because it is unclear which branch's metadata will apply to each file

This is a prototype version of a tool to demonstrate this model. The findings have been detailed in the following publication (not yet published):

Scott, Mark, Steven J. Johnston, and Simon J. Cox (2016). "Metagit: Decentralised Metadata Management With Git". In: *Information Systems*. DOI: [`10.1016/j.is.2016.09.002`](http://dx.doi.org/10.1016/j.is.2016.09.002). Forthcoming.

## Requirements

The tool has the following prerequisites:

* [libgit2](https://libgit2.github.com) - can be installed using MacPorts or HomeBrew
* [pygit2](http://www.pygit2.org) - can be installed using MacPorts or pip3
