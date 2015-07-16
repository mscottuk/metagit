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

class MetadataRequestError(Exception):
	"""The metadata request is not valid"""
	pass

class FileActions:
	dump = 1
	json = 2
	default = dump | json

	@staticmethod
	def is_action(action,actioncmp):
		return action & actioncmp == actioncmp


class MetadataBlob:
	def __init__(self,metadataitem,metadatafilename,metadatatree):
		self.metadatafilename=metadatafilename
		self.metadatatree=metadatatree
		self.metadataitem=metadataitem

class Metadata:

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
		self.rel_req_path = self.abs_req_path[len(self.base_path)+1:]

		if debug:
			print "Repo=" + self.repo_path
			print "Abs=" + self.abs_req_path
			print "Rel="+ self.rel_req_path

		# Find metadata branch
		self.find_metadata_branch()

	def find_metadata_branch(self):
		# Find metadata branch
		self.branch = self.repo.lookup_branch(self.branchname)

		# Find commit in metadata branch
		if self.branch is None:
			raise NoMetadataBranchError("Could not find metadata branch in the repository")

		self.branchref = self.repo.lookup_reference(self.branch.name)

		commit = self.branch.get_object()

		if not isinstance(commit,pygit2.Commit):
			raise NoMetadataBranchError("Could not find metadata branch with commit in the repository")

		self.commit=commit

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
					return MetadataBlob(metadataitem,metadatafilename,currenttree)
				else:
					raise MetadataBlobNotFoundError("Could not find metadata blob in the tree")
			else:									# We are not in the right tree so move onto the next tree
				nexttree=currenttree[nextitem]      # Find the sub-tree in the current tree
				nexttreeitem=self.repo[nexttree.id] # Retrieve the tree from the repository using its ID
				if isinstance(metadataitem,pygit2.Tree):
					print "Found next tree " + nextitem
					return self.get_blob(treelist[1:],nexttreeitem)
				else:
					raise MetadataTreeNotFoundError("Could not find metadata with path specified (Tree " + nextitem + " not found")
		except KeyError, e:
			raise MetadataBlobNotFoundError("No metadata found for " + e.message) # Metadata object does not exist yet

	def get_metadata_blob(self,path):
		return self.get_blob(path.split(os.sep),self.commit.tree)

	def save_metadata(self,jsondict,path):

		# Create an object to save in the repository
		newfile = json.dumps(jsondict)

		# Save the object into the repository
		newblobid = self.repo.create_blob(newfile)

		# Create a new tree with the blob in it, editing the last tree in the path if it exists.

		# Create a new tree which points to the blob's tree, editing the last but one tree in the path if it exists.

		# Recurse up the tree

		# WE CANNOT USE metadatatree ANY MORE.
		# Do some iteration here to work out our tree.
		# pathlist = path.split(os.sep)
		# if len(pathlist)==1 and len(pathlist[0])==0:

		if hasattr(self,'metadatatree'):
			treebuilder = self.repo.TreeBuilder(self.metadatatree)
		else:
			treebuilder = self.repo.TreeBuilder()

		treebuilder.insert(self.metadatafilename,newblobid,pygit2.GIT_FILEMODE_BLOB)
		treebuilderid = treebuilder.write()
		print "Tree saved as " + treebuilderid.__str__()

		# Create a commit
		commitid = self.repo.create_commit(self.branch.name,
			pygit2.Signature('Mark', 'cms4@soton.ac.uk'),
			pygit2.Signature('Mark', 'cms4@soton.ac.uk'),
			"Updated " + self.metadatafilename + " metadata",
			treebuilderid,
			[self.commit.id])

		# Update the branch's reference to point to the commit
		self.branchref.set_target(commitid,pygit2.Signature('Mark', 'cms4@soton.ac.uk'), "Updated " + self.metadatafilename + " metadata")
		print "Commit saved as " + commitid.__str__()

		#branchref.log_append(commitid, pygit2.Signature('Mark', 'cms4@soton.ac.uk'), "Updated " + self.metadatafilename + " metadata")

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

	def check_path_request(self,path):
		# Work out the path for the metadata request

		# If no path was specified, use the default for the repository object
		if path is None:
			path=self.rel_req_path

		# Remove start slash from the request as we start searching from the root anyway
		if os.path.isabs(path):
			path=path[1:]

		return path

	def print_metadata(self,fileaction,path=None):

		path=self.check_path_request(path)

		# Get the metadata
		metadata_blob = self.get_metadata_blob(path)

		gitblob = metadata_blob.metadataitem

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

	def update_metadata(self,k,v,path=None):

		path=self.check_path_request(path)

		try:
			# Get the metadata
			blob = self.get_metadata_blob(path)
			gitblob = blob.metadataitem
			blobdata = json.loads(gitblob.data)
		except MetadataBlobNotFoundError, e:
			blobdata = json.loads("{}")

		blobdata[k] = v
		self.save_metadata(blobdata,path)
