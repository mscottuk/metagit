#!/opt/local/bin/python

import json
import argparse
import os
import pygit2

class MetadataRepo:
	def __init__(self,args):
	
		# Parse the user arguments
		self.args = args
	
		if self.args.metadatafile is None:
			self.req_path=os.getcwd()
		else:
			self.req_path=self.args.metadatafile

		self.abs_req_path=os.path.abspath(self.req_path)

		if not os.path.exists(self.abs_req_path):
			if self.args.storeonly:
				# File does not exist, but have been asked to look in store
				# Will try to find a store in parent directory of requested file
				self.repopath=os.path.dirname(self.abs_req_path)
			else:
				print "File does not exist in folder. Please use --storeonly to check in metadata store anyway."
				raise IOError("File not found")
		else:
			# Requested path exists. Will use requested path as place to start looking for repository
			self.repopath=self.abs_req_path
						
		try:
			self.repodir = os.path.abspath(pygit2.discover_repository(self.repopath))
		except KeyError:
			print "Could not find a Git repository"
			raise

		self.repo = pygit2.Repository(self.repodir)
		self.basedir = os.path.dirname(self.repodir)
		self.rel_req_path=self.abs_req_path[len(self.basedir)+1:]
		
# 		if len(self.rel_req_path)==0:
# 			self.rel_req_path="_folder_metadata.json"

		if self.args.verbose:
			print "Repo=" + self.repodir
			print "Abs=" + self.abs_req_path
			print "Rel="+ self.rel_req_path

	def get_blob(self,treelist,currenttree):
		nextitem = treelist[0]
		try:
			if len(treelist)==1:
				if len(nextitem)==0:
					metadatafilename="_folder_metadata.json"
				else:
					metadatafilename=nextitem
				metadata=currenttree[metadatafilename]
				metadataitem=self.repo[metadata.id]
				if isinstance(metadataitem,pygit2.Blob):
					self.metadatafilename=metadatafilename
					self.metadatatree=currenttree # Save tree so we can access it later
					return metadataitem
				else:
					raise Exception("Item not found")
			else:
				nexttree=currenttree[nextitem]
				nexttreeitem=self.repo[nexttree.id]
				if isinstance(metadataitem,pygit2.Tree):
					print "Found next tree " + nextitem
					return self.get_blob(treelist[1:],nexttreeitem)
				else:
					raise Exception("No tree found")
		except KeyError:
			print "No metadata not found"
			raise				
	
	def get_metadata(self):
		self.branch = self.repo.lookup_branch(self.args.branch)
		branchobj = self.branch.get_object()
		self.commit = branchobj # Save commit for later
		tree = branchobj.tree
		
		blob = self.get_blob(self.rel_req_path.split(os.sep),tree)
		
		return blob
		
	def is_action(self,action):
		return self.args.action & action == action
		
	def save_metadata(self,jsondict):
		newfile = json.dumps(jsondict)
		newblobid = self.repo.create_blob(newfile)
		treebuilder = self.repo.TreeBuilder(self.metadatatree)
		treebuilder.insert(self.metadatafilename,newblobid,pygit2.GIT_FILEMODE_BLOB)
		treebuilderid = treebuilder.write()
		print "Tree saved as " + treebuilderid.__str__()
		commitid = self.repo.create_commit(self.branch.name,
			pygit2.Signature('Mark', 'cms4@soton.ac.uk'),
			pygit2.Signature('Mark', 'cms4@soton.ac.uk'),
			"Updated " + self.metadatafilename + " metadata",
			treebuilderid,
			[self.commit.id])
		branchref = self.repo.lookup_reference(self.branch.name)
		branchref.set_target(commitid,pygit2.Signature('Mark', 'cms4@soton.ac.uk'), "Updated " + self.metadatafilename + " metadata")
# 		branchref.log_append(commitid, pygit2.Signature('Mark', 'cms4@soton.ac.uk'), "Updated " + self.metadatafilename + " metadata")
		print "Commit saved as " + commitid.__str__()
			

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
		
