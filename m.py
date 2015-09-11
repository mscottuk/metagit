#!/opt/local/bin/python

import os
import sys
import json
import argparse
from ldc import *
import traceback
import re # Regular expressions


# 1) Get Git repo, specifying branch to use for metadata
# 2) Ask for metadata for specific file and revision

# Command line syntax:
#   m [-h] [--branch BRANCH] [-v] {get,add}
#   m add [-h] keyvaluepair [path]
#   m get [-h] [--storeonly] [--key KEY] [--dump | --json] [path]
#
# Examples:
#   m add author="Charles Darwin" orgin.pdf
#   m add title="On the Origin of Species" orgin.pdf
#   m get orgin.pdf
#   m get --key author origin.pdf

# class ParsePathAction(argparse.Action):
# 	branch_default = "metadata"
# 	stream_default = "metadata"
# 	path_default = os.getcwd()
# 	syntax = "(metadatapath | [branch:]metadatapath:stream)"
#
# 	def __call__(self, parser, namespace, values, option_string=None):
#
# 		# Regular expression:
# 		# first group can be blank (*) and is lazy (?), and is any char except ':'
# 		# second group can be blank (*) to allow e.g. 'branch::metadata' for current directory, and is any char except ':'
# 		# third group can be blank (*) and is lazy (?), and is any char except ':'
# 		# Separating ':'s are optional to allow for branch and stream to be dropped to activate defaults
# 		# dir                  = '', 'dir', ''
# 		# branch:dir:metadata  = 'branch','dir','metadata'
# 		# dir:metadata         = '','dir','metadata'
# 		# branch::metadata     = 'branch','','metadata'
# 		values_split = re.match(r'^([^:\r\n]*?):?([^:\r\n]*):?([^:\r\n]*?)$', values)
#
# 		# Wrong format received - possibly too many ':'s in string
# 		if values_split is None:
# 			parser.error("Could not parse '%s'. Please use syntax %s." % (values, ParsePathAction.syntax))
#
# 		branchname = values_split.group(1) or ParsePathAction.branch_default
# 		path       = values_split.group(2) or ParsePathAction.path_default
# 		streamname = values_split.group(3) or ParsePathAction.stream_default
#
# 		setattr(namespace, self.dest, values)
# 		setattr(namespace, 'branchname', branchname)
# 		setattr(namespace, 'metadatapath', path)
# 		setattr(namespace, 'streamname', streamname)


class ParsePathAndStream(argparse.Action):
	datarev_default = None
	stream_default = "metadata"
	path_default = os.getcwd()
	syntax = "datarev:metadatapath[:stream]"

	def __call__(self, parser, namespace, values, option_string=None):

		# Regular expression to parse the following expressions:
		# dir                  = '', 'dir', ''
		# branch:dir:metadata  = 'branch','dir','metadata'
		# branch:dir         = 'branch','dir',''
		# branch::metadata     = 'branch','','metadata'

		# Try branch:dir:metadata or branch:dir:'' first
		values_split = re.match(r'^([^:\r\n]*):([^:\r\n]*):?([^:\r\n]*)$', values)

		# Next, if that didn't work, try just matching dir
		if values_split is None:
			values_split = re.match(r'^()([^:\r\n]*)()$', values)

		# Wrong format received - possibly too many ':'s in string
		if values_split is None:
			parser.error("Could not parse '%s'. Please use syntax %s." % (values, ParsePathAndStream.syntax))

		datarev = values_split.group(1) or ParsePathAndStream.datarev_default
		path       = values_split.group(2) or ParsePathAndStream.path_default
		streamname = values_split.group(3) or ParsePathAndStream.stream_default

		setattr(namespace, self.dest, values)
		setattr(namespace, 'datarev', datarev)
		setattr(namespace, 'metadatapath', path)
		setattr(namespace, 'streamname', streamname)


# THIS ONE PARSES TWO PARTS:
# class ParsePathAndStream(argparse.Action):
# 	stream_default = "metadata"
# 	path_default = os.getcwd()
# 	syntax = "metadatapath[:stream]"
#
# 	def __call__(self, parser, namespace, values, option_string=None):
#
# 		# Regular expression:
# 		# first group can be blank (*) to allow e.g. 'branch::metadata' for current directory, and is any char except ':'
# 		# second group can be blank (*) and is lazy (?), and is any char except ':'
# 		# Separating ':'s are optional to allow for branch and stream to be dropped to activate defaults
# 		# dir                  = 'dir', ''
# 		# dir:metadata         = 'dir','metadata'
# 		# :metadata            = '','metadata'
# 		values_split = re.match(r'^([^:\r\n]*):?([^:\r\n]*?)$', values)
#
# 		# Wrong format received - possibly too many ':'s in string
# 		if values_split is None:
# 			parser.error("Could not parse '%s'. Please use syntax %s." % (values, ParseDataRef.syntax))
#
# 		path       = values_split.group(1) or ParsePathAndStream.path_default
# 		streamname = values_split.group(2) or ParsePathAndStream.stream_default
#
# 		setattr(namespace, self.dest, values)
# 		setattr(namespace, 'metadatapath', path)
# 		setattr(namespace, 'streamname', streamname)


class ParseMetadataRef(argparse.Action):
	metadataref_default = "refs/heads/metadata"

	def __call__(self, parser, namespace, values, option_string=None):

		# Check if we have an absolute reference path passed
		if values.startswith("refs/"):
			# Yes we have one so don't mess with it
			metadataref = values
		else:
			# We don't have one so generate it
			metadataref = "refs/heads/%s" % values

		setattr(namespace, self.dest, metadataref)

def parse_args():
	# Create command line parser
	parser = argparse.ArgumentParser(description='Manipulate a dataset\'s metadata')

	# Add top level arguments
	parser.add_argument('-v', '--verbose',
						action='store_true',
						default=False,
						help="Verbose output")

	# parser.add_argument('--rev',
	# 					dest="datarev",
	# 					default="HEAD",
	# 					help="The revision for which to view metadata")

	parser.add_argument('-m', '--metadataref',
						dest='metadataref',
						action=ParseMetadataRef,
						default = ParseMetadataRef.metadataref_default,
						help="A git reference to the metadata, e.g. 'metadata' or 'refs/heads/metadata'")

	# parser_group = parser.add_mutually_exclusive_group(required=True)
	#
	# parser_group.add_argument('-p', '--previous',
	# 					dest="previous",
	# 					action="store_true",
	# 					default=False,
	# 					help="Look back in metadata history to find where committed")
	#
	# parser_group.add_argument('-b', '--branch',
	# 					dest="previous",
	# 					action="store_false",
	# 					help="Do not look back in metadata history, use datarev to find metadata")

	# parser.set_defaults(metadatafrom='metadataref')

	# Add sub-parsers
	subparsers = parser.add_subparsers()

	parser_get = subparsers.add_parser('get')
	parser_get.set_defaults(command=get)
	parser_get.set_defaults(fileaction=FileActions.default)

	parser_set = subparsers.add_parser('set')
	parser_set.set_defaults(command=set)

	parser_list = subparsers.add_parser('list')
	parser_list.set_defaults(command=list)

	# Set up 'get' subparser
	parser_get.add_argument('path',
						nargs="?",
						default=ParsePathAndStream.path_default,
						action=ParsePathAndStream,
						help="%s The path to the metadata object. The default branch and stream will be used if not specified." % ParsePathAndStream.syntax)

	# parser_get.add_argument('-d', '--datarev',
	# 					dest='datarev',
	# 					default="HEAD",
	# 					help='The revision for which to view metadata')

	parser_get.add_argument('--key',
						help="The key to lookup")

	parser_get.add_argument('--value',
						help="The value it must have")


	parser_get_group = parser_get.add_mutually_exclusive_group()
	parser_get_group.add_argument('--dump',
						dest='fileaction',
						action='store_const',
						const=FileActions.dump,
						help='Do not parse the file in any way, just print it to stdout')

	parser_get_group.add_argument('--json',
						dest='fileaction',
						action='store_const',
						const=FileActions.json,
						help='Parse the file as JSON and prettify the output')

	# Set up 'set' subparser
	# parser_set.add_argument('-d', '--datarev',
	# 					dest='datarev',
	# 					default=None,
	# 					help='The revision for which to view metadata')

	parser_set.add_argument('keyvaluepair',
						help='Key value pair to add to metadata')

	parser_set.add_argument('path',
						nargs="?",
						default=ParsePathAndStream.path_default,
						action=ParsePathAndStream,
						help="%s The path to the metadata object. The default branch and stream will be used if not specified." % ParsePathAndStream.syntax)

	parser_set.add_argument('--force',
						action='store_true',
						default=False,
						help="Force any overwrites")

	# Set up 'list' subparser
	# parser_list.add_argument('-d', '--datarev',
	# 					dest='datarev',
	# 					default="HEAD",
	# 					help='The revision for which to view metadata')

	parser_list.add_argument('path',
						nargs="?",
						default=ParsePathAndStream.path_default,
						action=ParsePathAndStream,
						help="%s The path to the metadata object. The default branch and stream will be used if not specified." % ParsePathAndStream.syntax)

	args = parser.parse_args()

	if args.verbose:
		MetadataRepository.errormsg("** Parsed Arguments **")
		MetadataRepository.errormsg("Unparsed path : '%s'" % args.path)
		MetadataRepository.errormsg("datarev       : %s" % args.datarev)
		MetadataRepository.errormsg("metadatapath  : " + args.metadatapath)
		MetadataRepository.errormsg("stream        : " + args.streamname)
		MetadataRepository.errormsg("")

	return args


def get(args):
	# Check the data revision supplied
	if args.datarev is None:
		MetadataRepository.errormsg("\nData revision not supplied. Either specify a specific metadata revision (e.g. HEAD), one of the existing metadata entries for this object (listed below), or the commit this file was added on.\n")
		list(args)
		return

	repo = MetadataRepository(args.metadatapath, args.metadataref, debug=args.verbose)
	repo.print_metadata(args.streamname, args.datarev, fileaction=args.fileaction, keyfilter=args.key, valuefilter=args.value)


def set(args):
	# Check the data revision supplied
	if args.datarev is None:
		MetadataRepository.errormsg("\nData revision not supplied. Either specify a specific metadata revision (e.g. HEAD), one of the existing metadata entries for this object (listed below), or the commit this file was added on.\n")
		list(args)
		return

	# Separate the key and value
	k, sep, v = args.keyvaluepair.partition("=")

	# Check keyvaluepair argument is correct format
	if sep != "=":
		raise KeyValuePairArgumentError(KeyValuePairArgumentError.__doc__)

	repo = MetadataRepository(args.metadatapath, args.metadataref, debug=args.verbose)
	repo.update_metadata(k, v, args.streamname, args.datarev, force=args.force)


def list(args):
	repo = MetadataRepository(args.metadatapath, args.metadataref, debug=args.verbose)
	print "Metadata exists on the following commits:"
	repo.list_metadata_in_stream(args.datarev, args.streamname)


if __name__ == "__main__":

	# Parse the passed arguments, exiting if an unexpected error occurs
	args = parse_args()

	# Execute the requested function
	try:
		args.command(args)
	except Exception, e:
		if args.verbose:
			traceback.print_exc()
		else:
			exc_type, exc_obj, exc_tb = sys.exc_info()
			MetadataRepository.errormsg("%s: %s" % (exc_type.__name__, exc_obj))
