import os
import json
import pygit2
import hashlib

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

class MetadataWriteError(Exception):
	"""The metadata could not be written"""
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

	data_hash = hashlib.sha224('data').hexdigest()
	metadata_hash = hashlib.sha224('metadata').hexdigest()

	def __init__(self, req_path, branchname, streamname, storeonly, debug):

		# Save miscellaneous arguments
		self.branchname = branchname
		self.streamname = streamname
		self.storeonly = storeonly
		self.debug = debug

		# Sort out paths
		self.req_path = req_path
		self.abs_req_path=os.path.abspath(req_path)
		self.repo_path = self.get_repo_path(self.abs_req_path,storeonly)
		self.repo = pygit2.Repository(self.repo_path)
		self.base_path = os.path.dirname(self.repo_path)
		self.rel_req_path = self.abs_req_path[len(self.base_path)+1:]

		# Add the trailing slash if the user added one
		if self.req_path[-1] == os.sep and self.rel_req_path[-1] != os.sep:
			self.rel_req_path += os.sep

		self.debugmsg ("Repo=" + self.repo_path)
		self.debugmsg ("Abs=" + self.abs_req_path)
		self.debugmsg ("Rel="+ self.rel_req_path)

		# Find metadata branch
		self.find_metadata_branch()

	def debugmsg(self,msg):
		if self.debug:
			print msg

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
			if len(treelist)==1:
				if len(nextitem)==0:
					raise MetadataRequestError("The request was not valid - check the stream name")
				metadata=currenttree[nextitem]
				metadatablob=self.repo[metadata.id]
				if not isinstance(metadatablob,pygit2.Blob):
					raise MetadataBlobNotFoundError("Could not find metadata blob in the tree")
				return MetadataBlob(metadatablob,nextitem,currenttree)
				# metadata=currenttree[Metadata.metadata_hash] # Lookup metadata
				# metadatatree=self.repo[metadata.id]
				# if not isinstance(metadatatree,pygit2.Tree):
				# 	raise MetadataBlobNotFoundError("Could not find metadata tree")
				# metadataitem=metadatatree[streamname]
				# if not isinstance(metadataitem,pygit2.Blob):
				# 	raise MetadataBlobNotFoundError("Could not find metadata blob in the tree")
				# return MetadataBlob(metadataitem,metadatafilename,currenttree)
			else:									# We are not in the right tree so move onto the next tree
				nexttree=currenttree[nextitem]      # Find the sub-tree in the current tree
				nexttreeitem=self.repo[nexttree.id] # Retrieve the tree from the repository using its ID
				if isinstance(nexttreeitem,pygit2.Tree):
					self.debugmsg("Found next tree " + nextitem)
					return self.get_blob(treelist[1:],nexttreeitem)
				else:
					raise MetadataTreeNotFoundError("Could not find metadata with path specified (Tree %s not found)" % nextitem)
		except KeyError, e:
			raise MetadataBlobNotFoundError("No metadata found for " + e.message) # Metadata object does not exist yet

	def get_metadata_blob(self,path):
		parentspath = self.get_metadata_blob_path(path,self.streamname)
		parentslist = parentspath.split(os.sep)
		return self.get_blob(parentslist,self.commit.tree)

	def write_tree_hierarchy(self,parentslist,newentryid):
		newentry = self.repo[newentryid]

		# Get last entry as name of tree to save (work backwards in tree list)
		newentryname = parentslist[-1]

		# Use remaining entries as the parent tree's path
		# Python does the right thing here for most strings and lists so no need to check the length of parentslist
		metadatapath = os.sep.join(parentslist[0:-1])

		self.debugmsg("Looking for " + metadatapath + newentryname)

		try:
			tree = self.repo.revparse_single('{0}:{1}'.format(self.branch.name,metadatapath))
			if isinstance(tree,pygit2.Tree):
				# Found existing tree so modify it
				treebuilder = self.repo.TreeBuilder(tree)
			else:
				raise Exception("Expected Tree, got " + str(type(tree)))

		except KeyError:
			# Tree doesn't exist so create a new one
			treebuilder = self.repo.TreeBuilder()

		if isinstance(newentry, pygit2.Blob):
			print "Writing blob"
			# Create a new tree with the blob in it, editing the last tree in the path if it exists.
			treebuilder.insert(newentryname,newentry.id,pygit2.GIT_FILEMODE_BLOB)
		elif isinstance(newentry, pygit2.Tree):
			print "Writing tree"
			# Create a new tree which points to the blob's tree, editing the last but one tree in the path if it exists.
			treebuilder.insert(newentryname,newentry.id,pygit2.GIT_FILEMODE_TREE)
		else:
			raise Exception("Expected Blob or Tree, got " + str(type(newentry)))

		treebuilderid = treebuilder.write()

		self.debugmsg("Tree saved as " + treebuilderid.__str__())

		if len(parentslist) > 1:
			# Recurse up the tree, pass modified tree to next call of function
			return self.write_tree_hierarchy(parentslist[0:-1],treebuilderid)
		else:
			return treebuilderid

	# def write_metadata_tree_hierarchy(self,parentslist,newentryid):
	# 	newentry = self.repo[newentryid]
	# 	nextitem = parentslist[-1]   # Get last entry (work backwards in tree list)
	#
	# 	 # Python does the right thing here for most strings and lists so no need to check the length of parentslist
	# 	metadatapath = os.sep.join(parentslist[0:-1])
	#
	# 	newentryname = self.streamname #"_folder_metadata.json" # Folder metadata
	#
	#    	# This is the first time this has been called so there is no tree to link to
	# 	# We have an empty string so the path points to a folder
	# 	if isinstance(newentry, pygit2.Blob)
	# 		parentname = Metadata.metadata_hash
	# 	else:
	# 		parentname = nextitem
	#
	# 	self.debugmsg("Looking for " + metadatapath + newentryname)
	#
	# 	try:
	# 		tree = self.repo.revparse_single('{0}:{1}'.format(self.branch.name,metadatapath))
	# 		treebuilder = self.repo.TreeBuilder(tree)
	# 	except KeyError:
	# 		treebuilder = self.repo.TreeBuilder()
	#
	# 	if isinstance(newentry, pygit2.Blob):
	# 		print "Writing blob"
	# 		# Create a new tree with the blob in it, editing the last tree in the path if it exists.
	# 		treebuilder.insert(newentryname,newentry.id,pygit2.GIT_FILEMODE_BLOB)
	# 	elif isinstance(newentry, pygit2.Tree):
	# 		print "Writing tree"
	# 		# Create a new tree which points to the blob's tree, editing the last but one tree in the path if it exists.
	# 		treebuilder.insert(newentryname,newentry.id,pygit2.GIT_FILEMODE_TREE)
	# 	else:
	# 		raise Exception("Expected blob or tree, got " + str(type(newentry)))
	#
	# 	treebuilderid = treebuilder.write()
	#
	# 	self.debugmsg("Tree saved as " + treebuilderid.__str__())
	#
	# 	if len(parentslist) > 1:
	# 		# Recurse up the tree, pass modified tree to next call of function
	# 		return self.write_tree_hierarchy(parentslist[0:-1],treebuilderid)
	# 	else:
	# 		return treebuilderid

	def get_metadata_blob_path(self,path,streamname):
		parentspath = os.sep.join([path, Metadata.metadata_hash, streamname])
		if os.path.isabs(parentspath):
			parentspath=parentspath[1:]
		self.debugmsg("parentspath = " + parentspath)
		return parentspath

	def save_file(self,newfile,path):
		# Save the object into the repository
		newblobid = self.repo.create_blob(newfile)

		# Save metadata tree
		parentspath = self.get_metadata_blob_path(path,self.streamname)
		parentslist = parentspath.split(os.sep)
		toptreeid = self.write_tree_hierarchy(parentslist, newblobid)

		# Create a commit
		commitid = self.repo.create_commit(self.branch.name,
			pygit2.Signature('Mark', 'cms4@soton.ac.uk'),
			pygit2.Signature('Mark', 'cms4@soton.ac.uk'),
			"Updated metadata for " + path,
			toptreeid,
			[self.commit.id])
		# Update the branch's reference to point to the commit
		# self.branchref.set_target(commitid,pygit2.Signature('Mark', 'cms4@soton.ac.uk'), "Updated metadata")

		self.debugmsg("Commit saved as " + commitid.__str__())

		return commitid

	def save_metadata(self,jsondict,path):

		# Create an object to save in the repository
		newfile = json.dumps(jsondict)

		commitid = self.save_file(newfile,path)

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

	def print_metadata(self,fileaction,path=None,keyfilter=None,valuefilter=None):

		path=self.check_path_request(path)

		# Get the metadata
		metadata_blob = self.get_metadata_blob(path)

		gitblob = metadata_blob.metadataitem

		if FileActions.is_action(fileaction,FileActions.json):
			try:
				self.printjson(gitblob,keyfilter,valuefilter)
			except ValueError:
				if FileActions.is_action(fileaction,FileActions.dump):
					self.dumpfile(gitblob)
				else:
					raise MetadataFileFormatError("Not JSON data. Use --dump to show file anyway.")
		elif FileActions.is_action(fileaction,FileActions.dump):
			self.dumpfile(gitblob)

	def printjson(self,gitblob,keyfilter=None,valuefilter=None):
		data = json.loads(gitblob.data)
		for key, value in data.iteritems():
			if (keyfilter is None or keyfilter==key.__str__()) and (valuefilter is None or valuefilter==value.__str__()):
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
		except (MetadataBlobNotFoundError, MetadataTreeNotFoundError):
			blobdata = json.loads("{}")

		blobdata[k] = v
		self.save_metadata(blobdata,path)
