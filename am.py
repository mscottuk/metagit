#!/opt/local/bin/python

import json
import argparse
from ldc import MetadataRepo
		

def printjson(blob):
	data = json.loads(blob.data)
	for key, value in data.iteritems():
	  print '{:<20} {:<20}'.format(key,  value)

def dumpfile(blob):
	print blob.data
  
def parse_args():
	parser = argparse.ArgumentParser(description='Manipulate a dataset\'s metadata')

	parser.add_argument('keyvaluepair',
						nargs='?',
						default='Key value pair to add')
						
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
						
	args = parser.parse_args()
	return args


if __name__ == "__main__":

	try:
		args = parse_args()
		state = MetadataRepo(args)
		
		try:
			blobdata = json.loads(state.get_metadata().data)
		except KeyError:
			blobdata = json.loads('')
			
		k, sep, v = args.keyvaluepair.partition("=")
		if sep:
			blobdata[k] = v
			state.save_metadata(blobdata)
# 			for key,value in blobdata.iteritems():
# 				print '{:<20} {:<20}'.format(key,  value)
			
		else:
			print "Not in key=value format"
			
		
		exit()
						
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
		
