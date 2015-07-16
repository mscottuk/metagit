#!/opt/local/bin/python

import os
import sys
import json
import argparse
from ldc import *
import traceback

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


def parse_args():
	# Create command line parser
	parser = argparse.ArgumentParser(description='Manipulate a dataset\'s metadata')

	# Add top level arguments
	parser.add_argument('--branch',
						default="metadata",
						help="The git branch to use for metadata")

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
						default=os.getcwd(),
						help='The name of the metadata object')

	# Set up 'get' subparser
	parser_get.add_argument('path',
						nargs="?",
						default=os.getcwd(),
						help='The name of the metadata object')

	parser_get.add_argument('--storeonly',
						action='store_true',
						default=False,
						help="The file specified only exists in the metadata store and does not have a matching file in the filesystem")

	parser_get.add_argument('--key',
						help="The key to lookup")

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

	return args

def get(args):
	try:
		repo = Metadata(args.path, args.branch, args.storeonly, args.verbose)
		repo.print_metadata(args.fileaction)
	except MatchingDataNotFoundError, e:
		# Change the error message to include --storeonly argument
		raise MatchingDataNotFoundError(e.message + ". Please use --storeonly to check in metadata store anyway.")

def set(args):
	# Separate the key and value
	k, sep, v = args.keyvaluepair.partition("=")

	# Check keyvaluepair argument is correct format
	if sep != "=":
		raise KeyValuePairArgumentError(KeyValuePairArgumentError.__doc__)

	repo = Metadata(args.path, args.branch, storeonly=False, debug=args.verbose)

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
