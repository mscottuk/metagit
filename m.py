#!/opt/local/bin/python

import os
import sys
import json
import argparse
from ldc import *
import traceback
import re  # Regular expressions


# 1) Get Git repo, specifying branch to use for metadata
# 2) Ask for metadata for specific file and revision

# Command line syntax:
#   m [-h] [--branch BRANCH] [-v] {get,add}
#   m add [-h] keyvaluepair [path]
#   m get [-h] [--storeonly] [--key KEY] [--dump | --json] [path]
#
# Examples:
#   m add author="Charles Darwin" origin.pdf
#   m add title="On the Origin of Species" origin.pdf
#   m get origin.pdf
#   m get --key author origin.pdf

class ParseMetadataRef(argparse.Action):

	def __call__(self, parser, namespace, values, option_string=None):

		# Check if we have an absolute reference path passed
		if values.startswith("refs/"):
			# Yes we have one so don't mess with it
			metadataref = values
		else:
			# We don't have one so generate it
			metadataref = "refs/heads/%s" % values

		setattr(namespace, self.dest, metadataref)


class ParseDataRevisionMetadataSearchMethod(argparse.Action):

	def __call__(self, parser, namespace, values, option_string=None):

		# Check if we have an absolute reference path passed
		if values == "searchback":
			setattr(namespace, self.dest, DataRevisionMetadataSearchMethod.SearchBackForEarlierMetadataAllowed)
		elif values == "nosearchback":
			# We don't have one so generate it
			setattr(namespace, self.dest, DataRevisionMetadataSearchMethod.UseRevisionSpecifiedOnly)
		else:
			parser.error("Please specify 'searchback' or 'nosearchback'")


def parse_args():
	# Create command line parser
	parser = argparse.ArgumentParser(description='Manipulate a dataset\'s metadata')

	# Add top level arguments
	parser.add_argument(
		'-v', '--verbose',
		action='store_true',
		default=False,
		help="Verbose output")

	parser.add_argument(
		'-m', '--metadataref',
		dest='metadataref',
		action=ParseMetadataRef,
		default=MetadataRepository.metadataref_default,
		help="A git reference to the metadata, e.g. 'metadata' or 'refs/heads/metadata'")

	# Add sub-parsers
	subparsers = parser.add_subparsers()

	parser_get = subparsers.add_parser('get')
	parser_get.set_defaults(command=get)

	parser_set = subparsers.add_parser('set')
	parser_set.set_defaults(command=set)

	parser_list = subparsers.add_parser('list')
	parser_list.set_defaults(command=list)

	parser_copy = subparsers.add_parser('copy')
	parser_copy.set_defaults(command=copy)
	
	parser_log = subparsers.add_parser('log')
	parser_log.set_defaults(command=log)

	parser_setvalue = subparsers.add_parser('setvalue')
	parser_setvalue.set_defaults(command=setvalue)

	parser_getvalue = subparsers.add_parser('getvalue')
	parser_getvalue.set_defaults(command=getvalue)
	
	parser_ls = subparsers.add_parser('ls')
	parser_ls.set_defaults(command=ls) 

	# Set up 'get' subparser
	parser_get.add_argument(
		'path',
		nargs="?",
		default=os.getcwd(),
		help="%s The path to the metadata object. The default branch and stream will be used if not specified." % MetadataPath.path_syntax)
		
	# Set up the 'set' subparser
	parser_set.add_argument(
		'path',
		nargs="?",
		default=os.getcwd(),
		help="%s The path to the metadata object. The default branch and stream will be used if not specified." % MetadataPath.path_syntax)

	parser_set.add_argument('infile', type=argparse.FileType('r'))

	parser_set.add_argument(
		'--force',
		action='store_true',
		default=False,
		help="Force any overwrites")

	# Set up the 'list' subparser
	parser_list.add_argument(
		'path',
		nargs="?",
		default=os.getcwd(),
		help="%s The path to the metadata object. The default branch and stream will be used if not specified." % MetadataPath.path_syntax)


	# Set up the 'copy' subparser
	parser_copy.add_argument(
		'sourcepath',
		nargs="?",
		default=os.getcwd(),
		help="%s The path to the metadata object. The default branch and stream will be used if not specified." % MetadataPath.path_syntax)

	parser_copy.add_argument(
		'destpath',
		nargs="?",
		default=os.getcwd(),
		help="%s The path to the metadata object. The default branch and stream will be used if not specified." % MetadataPath.path_syntax)

	parser_copy.add_argument(
		'--force',
		action='store_true',
		default=False,
		help="Force any overwrites")


	# Set up the 'log' subparser
	parser_log.add_argument(
		'path',
		nargs="?",
		default=os.getcwd(),
		help="%s The path to the metadata object. The default branch and stream will be used if not specified." % MetadataPath.path_syntax)


	# Set up the 'ls' subparser
	parser_ls.add_argument(
		'path',
		nargs="?",
		default=os.getcwd(),
		help="%s The path to the metadata object. The default branch and stream will be used if not specified." % MetadataPath.path_syntax)


	# Set up the 'setvalue' subparser
	parser_setvalue.add_argument(
		'path',
		nargs="?",
		default=os.getcwd(),
		help="%s The path to the metadata object. The default branch and stream will be used if not specified." % MetadataPath.path_syntax)

	parser_setvalue.add_argument(
		'keyvaluepair',
		help='Key value pair to add to metadata')


	# Set up the 'getvalue' subparser
	parser_getvalue.add_argument(
		'path',
		nargs="?",
		default=os.getcwd(),
		help="%s The path to the metadata object. The default branch and stream will be used if not specified." % MetadataPath.path_syntax)

	parser_getvalue.add_argument(
		'keyfilter',
		nargs="?",
		help='Key value pair to add to metadata')


	args = parser.parse_args()

	return args


def get(args, repo):

	metadatablob = repo.get_metadata_blob(args.path)
	sys.stdout.write(metadatablob.data)


def getvalue(args, repo):
	
	metadatablob = repo.get_metadata_blob(args.path)
	data = json.loads(metadatablob.data)
	for key, value in data.iteritems():
		if (args.keyfilter is None or args.keyfilter == key.__str__()):
			print '{:<20} {:<20}'.format(key, value)


def set(args, repo):

	repo.save_metadata_blob(args.path, args.infile.read())


def setvalue(args, repo):
	# Separate the key and value
	k, sep, v = args.keyvaluepair.partition("=")

	# Check keyvaluepair argument is correct format
	if sep != "=":
		raise KeyValuePairArgumentError(KeyValuePairArgumentError.__doc__)

	try:
		# Get the metadata
		metadatablob = repo.get_metadata_blob(args.path)
		jsondict = json.loads(metadatablob.data)
	except (MetadataBlobNotFoundError, NoMetadataBranchError):
		jsondict = json.loads("{}")

	# Update dictionary
	jsondict[k] = v

	# Create an object to save in the repository
	newfile = json.dumps(jsondict)

	commitid = repo.save_metadata_blob(args.path, newfile)


def list(args, repo):

	repo.list_metadata_in_stream(args.path)


def log(args, repo):

	repo.log(args.path)


def ls(args, repo):

	repo.list_metadata_objects()


def copy(args, repo):

	if args.verbose:
		MetadataRepository.errormsg("** Parsed Arguments **")
		MetadataRepository.errormsg("Unparsed path : '%s'" % args.sourcepath)
		MetadataRepository.errormsg("datarev       : %s" % args.sourcepath_datarev)
		MetadataRepository.errormsg("metadatapath  : " + args.sourcepath_metadatapath)
		MetadataRepository.errormsg("stream        : " + args.sourcepath_streamname)
		MetadataRepository.errormsg("")
		MetadataRepository.errormsg("Unparsed path : '%s'" % args.destpath)
		MetadataRepository.errormsg("datarev       : %s" % args.destpath_datarev)
		MetadataRepository.errormsg("metadatapath  : " + args.destpath_metadatapath)
		MetadataRepository.errormsg("stream        : " + args.destpath_streamname)
		MetadataRepository.errormsg("")

	repo.copy_metadata(args.sourcepath, args.destpath, force=args.force)


if __name__ == "__main__":

	# Parse the passed arguments, exiting if an unexpected error occurs
	args = parse_args()

	# Execute the requested function
	try:
		repopath = MetadataRepository.discover_repository(args.path, args.metadataref)
		repo = MetadataRepository(repopath, debug=args.verbose)
		args.command(args, repo)
	except Exception, e:
		if args.verbose:
			traceback.print_exc()
		else:
			exc_type, exc_obj, exc_tb = sys.exc_info()
			MetadataRepository.errormsg("%s: %s" % (exc_type.__name__, exc_obj))
		sys.exit(1)
