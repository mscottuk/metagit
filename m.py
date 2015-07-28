#!/opt/local/bin/python

import os
import sys
import json
import argparse
from ldc import *
import traceback
import re # Regular expressions

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

class ParsePathAction(argparse.Action):
	branch_default = "metadata"
	stream_default = "metadata"
	path_default = os.getcwd()
	syntax = "(metadatapath | [branch:]metadatapath:stream)"

	def __call__(self, parser, namespace, values, option_string=None):

		# Regular expression:
		# first group can be blank (*) and is lazy (?), and is any char except ':'
		# second group can be blank (*) to allow e.g. 'branch::metadata' for current directory, and is any char except ':'
		# third group can be blank (*) and is lazy (?), and is any char except ':'
		# Separating ':'s are optional to allow for branch and stream to be dropped to activate defaults
		# dir                  = '', 'dir', ''
		# branch:dir:metadata  = 'branch','dir','metadata'
		# dir:metadata         = '','dir','metadata'
		# branch::metadata     = 'branch','','metadata'
		values_split = re.match(r'^([^:\r\n]*?):?([^:\r\n]*):?([^:\r\n]*?)$', values)

		# Wrong format received - possibly too many ':'s in string
		if values_split is None:
			parser.error("Could not parse '%s'. Please use syntax %s." % (values, ParsePathAction.syntax))

		branchname = values_split.group(1) or ParsePathAction.branch_default
		path       = values_split.group(2) or ParsePathAction.path_default
		streamname = values_split.group(3) or ParsePathAction.stream_default

		setattr(namespace, self.dest, values)
		setattr(namespace, 'branchname', branchname)
		setattr(namespace, 'metadatapath', path)
		setattr(namespace, 'streamname', streamname)

def parse_args():
	# Create command line parser
	parser = argparse.ArgumentParser(description='Manipulate a dataset\'s metadata')

	# Add top level arguments
	parser.add_argument('-v', '--verbose',
						action='store_true',
						default=False,
						help="Verbose output")

	# Add sub-parsers
	subparsers = parser.add_subparsers()

	parser_get = subparsers.add_parser('get')
	parser_get.set_defaults(command=get)
	parser_get.set_defaults(fileaction=FileActions.default)

	parser_set = subparsers.add_parser('set')
	parser_set.set_defaults(command=set)

	# Set up 'set' subparser
	parser_set.add_argument('keyvaluepair',
						help='Key value pair to add to metadata')

	parser_set.add_argument('path',
						nargs="?",
						default=ParsePathAction.path_default,
						action=ParsePathAction,
						help="%s The path to the metadata object. The default branch and stream will be used if not specified." % ParsePathAction.syntax)

	# Set up 'get' subparser
	parser_get.add_argument('path',
						nargs="?",
						default=ParsePathAction.path_default,
						action=ParsePathAction,
						help="%s The path to the metadata object. The default branch and stream will be used if not specified." % ParsePathAction.syntax)

	parser_get.add_argument('--storeonly',
						action='store_true',
						default=False,
						help="The file specified only exists in the metadata store and does not have a matching file in the filesystem")

	parser_get.add_argument('--key',
						help="The key to lookup")

	parser_get.add_argument('--value',
						help="The value it must have")


	group = parser_get.add_mutually_exclusive_group()
	group.add_argument('--dump',
						dest='fileaction',
						action='store_const',
						const=FileActions.dump,
						help='Do not parse the file in any way, just print it to stdout')

	group.add_argument('--json',
						dest='fileaction',
						action='store_const',
						const=FileActions.json,
						help='Parse the file as JSON and prettify the output')

	args = parser.parse_args()

	if args.verbose:
		print "path specified: " + args.path
		print "branch        : " + args.branchname
		print "metadatapath  : " + args.metadatapath
		print "stream        : " + args.streamname

	return args


def get(args):
	try:
		repo = Metadata(args.metadatapath, args.branchname, args.streamname, args.storeonly, args.verbose)
		repo.print_metadata(args.fileaction,keyfilter=args.key,valuefilter=args.value)
	except MatchingDataNotFoundError, e:
		# Change the error message to include --storeonly argument
		raise MatchingDataNotFoundError(e.message + ". Please use --storeonly to check in metadata store anyway.")

def set(args):
	# Separate the key and value
	k, sep, v = args.keyvaluepair.partition("=")

	# Check keyvaluepair argument is correct format
	if sep != "=":
		raise KeyValuePairArgumentError(KeyValuePairArgumentError.__doc__)

	repo = Metadata(args.metadatapath, args.branchname, args.streamname, storeonly=False, debug=args.verbose)

	repo.update_metadata(k,v)

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
			print e
