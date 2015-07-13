#!/opt/local/bin/python

import json
import argparse
from ldc import MetadataRepo

# import os
# import sys
# import pygit2
# from pprint import pprint

# metadata_folder="_metadata"

class FileActions:
	dump = 1
	json = 2
	default = dump | json
	
	
# Find the folder storing the metadata.
# This is inspired by Mercurial's approach of looking for an .hg folder
# in a higher parent directory
# def findmetadata(p):
#   while not os.path.isdir(os.path.join(p, metadata_folder)):
#     oldp, p = p, os.path.dirname(p)
#     if p == oldp:
#       return None
# 
#   return p
# 


def printjson(blob):
	data = json.loads(blob.data)
	for key, value in data.iteritems():
	  print '{:<20} {:<20}'.format(key,  value)

def dumpfile(blob):
	print blob.data
  
def parse_args():
	parser = argparse.ArgumentParser(description='Manipulate a dataset\'s metadata')

	parser.add_argument('metadatafile', 
						nargs='?',
						default=None,
						help='The name of the metadata object')
						
	parser.add_argument('--branch',
						default="metadata",
						help="The git branch to use for metadata")

	parser.add_argument('--storeonly',
						action='store_true',
						default=False,
						help="The file specified only exists in the metadata store and does not have a matching file in the filesystem")
						
	parser.add_argument('-v', '--verbose',
						action='store_true',
						default=False,
						help="Verbose output")				

	group = parser.add_mutually_exclusive_group()
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
		

	parser.set_defaults(action=FileActions.default)
						
	args = parser.parse_args()
	return args


if __name__ == "__main__":

	try:
		args = parse_args()
		state = MetadataRepo(args)
		blob = state.get_metadata()
						
		if state.is_action(FileActions.json):
			try:
				printjson(blob)
			except ValueError:
				if state.is_action(FileActions.dump):
					dumpfile(blob)
				else:
					print "Not JSON data. Use --dump to show file anyway."
		elif state.is_action(FileActions.dump):
			dumpfile(blob)
	except:
		if args.verbose:
			raise
		else:
			exit()
		
