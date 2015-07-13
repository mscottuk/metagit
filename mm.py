#!/opt/local/bin/python

import sys
import json
import argparse
from ldc import MetadataRepo
import traceback

#--lm

verbose = True

class FileActions:
	dump = 1
	json = 2
	default = dump | json

def printjson(blob):
	data = json.loads(blob.data)
	for key, value in data.iteritems():
	  print '{:<20} {:<20}'.format(key,  value)

def dumpfile(blob):
	print blob.data
  
def parse_args():
	# Create command line parser
	parser = argparse.ArgumentParser(description='Manipulate a dataset\'s metadata')
	
	# Add sub-parsers
	subparsers = parser.add_subparsers()

	# Add top level arguments
	parser.add_argument('--path', 
						default=None,
						help='The name of the metadata object')

	parser.add_argument('--branch',
						default="metadata",
						help="The git branch to use for metadata")

	parser.add_argument('-v', '--verbose',
						action='store_true',
						default=False,
						help="Verbose output")				

	parser_list = subparsers.add_parser('list')
	parser_list.set_defaults(func=list)
	parser_list.set_defaults(action=FileActions.default)

	parser_add = subparsers.add_parser('add')
	parser_add.set_defaults(func=add)


	# Set up 'add' subparser
	parser_add.add_argument('keyvaluepair',
						nargs='?',
						help='Key value pair to add to metadata')

	# Set up 'list' subparser
	parser_list.add_argument('--storeonly',
						action='store_true',
						default=False,
						help="The file specified only exists in the metadata store and does not have a matching file in the filesystem")
						
	group = parser_list.add_mutually_exclusive_group()
	group.add_argument('--dump',
						dest='action',
						action='store_const',
						const=FileActions.dump,
						help='Do not parse the file in any way, just print it to stdout')
						
	group.add_argument('--json',
						dest='action',
						action='store_const',
						const=FileActions.json,
						help='Parse the file as JSON and prettify the output')

	args = parser.parse_args()
	
	global verbose
	verbose = args.verbose
	
	return args
	
def list(args,repo):
	blob = repo.get_metadata()

	if repo.is_action(FileActions.json):
		try:
			printjson(blob)
		except ValueError:
			if repo.is_action(FileActions.dump):
				dumpfile(blob)
			else:
				print "Not JSON data. Use --dump to show file anyway."
	elif repo.is_action(FileActions.dump):
		dumpfile(blob)


def add(args,repo):

	if args.keyvaluepair is None:
		print "Not in key=value format"
		return

	try:
		blob = repo.get_metadata()
		blobdata = json.loads(blob.data)
	except MetadataRepo.MetadataBlobNotFoundError, e:
		blobdata = json.loads("{}")

	k, sep, v = args.keyvaluepair.partition("=")
	if sep:
		blobdata[k] = v
		repo.save_metadata(blobdata)		
	else:	
		print "Not in key=value format"

if __name__ == "__main__":

	try:
		args = parse_args()
		repo = MetadataRepo(args)
		args.func(args,repo)

	except Exception, e:
		if verbose:
			traceback.print_exc()
		else:
			print e
