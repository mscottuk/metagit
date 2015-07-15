import os
import json
import pygit2

class NoRepositoryError(Exception):
	"""Could not find a Git repository"""
	pass

class NoMetadataBranchError(Exception):
	"""Could not find a metadata branch in the repository"""
	pass

class MetadataBlobNotFoundError(Exception):
	"""Could not find metadata blob in the tree"""
	pass

class MetadataTreeNotFoundError(Exception):
	"""Could not find metadata with path specified (tree with specified name not found)"""
	pass

class MatchingDataNotFoundError(Exception):
	"""File does not exist in folder"""
	pass

class MetadataFileFormatError(Exception):
	"""File is not in correct format"""
	pass

class KeyValuePairArgumentError(Exception):
	"""Key value pair is not in key=value format"""
	pass

class FileActions:
	dump = 1
	json = 2
	default = dump | json

	@staticmethod
	def is_action(action,actioncmp):
		return action & actioncmp == actioncmp

class MetadataRepo:

	def __init__(self, req_path, branchname, storeonly, debug):

		# Save miscellaneous arguments
		self.branchname = branchname
		self.storeonly = storeonly
		self.debug = debug

		# Sort out paths
		self.req_path = req_path
		self.abs_req_path=os.path.abspath(req_path)
		self.repo_path = self.get_repo_path(self.abs_req_path,storeonly)
		self.repo = pygit2.Repository(self.repo_path)
		self.base_path = os.path.dirname(self.repo_path)
		self.rel_req_path=self.abs_req_path[len(self.base_path)+1:]

		if debug:
			print "Repo=" + self.repo_path
			print "Abs=" + self.abs_req_path
			print "Rel="+ self.rel_req_path

	def get_blob(self,treelist,currenttree):
		nextitem = treelist[0]
		try:
			if len(treelist)==1:					# Check if we are in the required metadata tree
				if len(nextitem)==0:				# Check if we have a name for the metadata, otherwise use default
					metadatafilename="_folder_metadata.json"
				else:
					metadatafilename=nextitem
				metadata=currenttree[metadatafilename] # Lookup metadata
				metadataitem=self.repo[metadata.id]
				if isinstance(metadataitem,pygit2.Blob):
					self.metadatafilename=metadatafilename
					self.metadatatree=currenttree # Save tree so we can access it later
					return metadataitem
				else:
					raise MetadataBlobNotFoundError("Could not find metadata blob in the tree")
			else:
				nexttree=currenttree[nextitem]
				nexttreeitem=self.repo[nexttree.id]
				if isinstance(metadataitem,pygit2.Tree):
					print "Found next tree " + nextitem
					return self.get_blob(treelist[1:],nexttreeitem)
				else:
					raise MetadataTreeNotFoundError("Could not find metadata with path specified (Tree " + nextitem + " not found")
		except KeyError, e:
			raise MetadataBlobNotFoundError("No metadata found for " + e.__str__())

	def get_metadata_blob(self):
		self.branch = self.repo.lookup_branch(self.branchname)

		if self.branch is None:
			raise NoMetadataBranchError("Could not find metadata branch in the repository")
		else:
			self.commit = self.branch.get_object() # Save commit for later
			tree = self.commit.tree

			blob = self.get_blob(self.rel_req_path.split(os.sep),tree)
			return blob

	def save_metadata(self,jsondict):
		newfile = json.dumps(jsondict)
		newblobid = self.repo.create_blob(newfile)

		if hasattr(self,'metadatatree'):
			treebuilder = self.repo.TreeBuilder(self.metadatatree)
		else:
			treebuilder = self.repo.TreeBuilder()

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

	def get_repo_path(self,abs_req_path,storeonly):
		if os.path.exists(abs_req_path):
			# Requested path exists. Will use requested path as place to start looking for repository
			repo_start_path=abs_req_path
		elif storeonly:
			# Path does not exist, but have been asked to look in store
			# Will try to find a store in parent directory of requested file
			repo_start_path=os.path.dirname(abs_req_path)
		else:
			# Path does not exist so we will not proceed any further
			raise MatchingDataNotFoundError("Matching data file does not exist in folder")

		try:
			repo_path = os.path.abspath(pygit2.discover_repository(repo_start_path))
		except KeyError:
			raise NoRepositoryError("Could not find a Git repository")

		return repo_path

	def print_metadata(self,fileaction):
		gitblob = self.get_metadata_blob()

		if FileActions.is_action(fileaction,FileActions.json):
			try:
				self.printjson(gitblob)
			except ValueError:
				if FileActions.is_action(fileaction,FileActions.dump):
					self.dumpfile(gitblob)
				else:
					raise MetadataFileFormatError("Not JSON data. Use --dump to show file anyway.")
		elif FileActions.is_action(fileaction,FileActions.dump):
			self.dumpfile(gitblob)

	def printjson(self,gitblob):
		data = json.loads(gitblob.data)
		for key, value in data.iteritems():
		  print '{:<20} {:<20}'.format(key,  value)

	def dumpfile(self,gitblob):
		print gitblob.data

	def update_metadata(self,k,v):
		try:
			blob = self.get_metadata_blob()
			blobdata = json.loads(blob.data)
		except MetadataBlobNotFoundError, e:
			blobdata = json.loads("{}")

		blobdata[k] = v
		self.save_metadata(blobdata)
