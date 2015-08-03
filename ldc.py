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

class NoDataError(Exception):
	"""Could not find matching data"""
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

class TextColor:
	Red = '\033[31m'
	Reset = '\033[0m'

class MetadataContainer:
	def __init__(self,metadatablob,datablob,datachanged):
		self.metadatablob = metadatablob
		self.datablob = datablob
		self.datachanged = datachanged
# 	def __init__(self,metadataitem,metadatafilename,metadatatree):
# 		self.metadatafilename=metadatafilename
# 		self.metadatatree=metadatatree
# 		self.metadataitem=metadataitem

class Metadata:

	data_hash = hashlib.sha224('data').hexdigest()
	metadata_hash = hashlib.sha224('metadata').hexdigest()

	def __init__(self, datarev, req_path, debug):

		# Save miscellaneous arguments
		self.debug = debug

		# Sort out paths
		self.req_path = req_path
		self.abs_req_path=os.path.abspath(req_path)
		self.repo_path = self.find_repository_path(self.abs_req_path)
		self.repo = pygit2.Repository(self.repo_path)
		self.base_path = os.path.dirname(self.repo_path)
		self.rel_req_path = self.abs_req_path[len(self.base_path)+1:]

		# Add the trailing slash if the user added one
		# if self.req_path[-1] == os.sep and self.rel_req_path[-1] != os.sep:
		# 	self.rel_req_path += os.sep

		self.debugmsg ("Repo=" + self.repo_path)
		self.debugmsg ("Abs=" + self.abs_req_path)
		self.debugmsg ("Rel="+ self.rel_req_path)

		self.datarev = datarev
		self.datarootcommit = self.find_data_commit(datarev)


	def debugmsg(self,msg):
		if self.debug:
			print msg

	def find_repository_path(self,abs_req_path):
		repo_search_path=abs_req_path
		found = False

		while not found:
			try:
				repo_path = os.path.abspath(pygit2.discover_repository(repo_search_path))
				found = True
			except KeyError:
				# Break if we have a blank string or have reached the root directory
				if repo_search_path in ["", os.path.abspath(os.sep)]:
					break
				# Otherwise, carry on looking up the tree
				else:
					repo_search_path = os.path.dirname(repo_search_path)

		if found:
			return repo_path
		else:
			raise NoRepositoryError("Could not find a Git repository")

	def find_data_commit(self,datarev):
		try:
			commit = self.repo.revparse_single(datarev)
			if not isinstance(commit,pygit2.Commit):
				raise NoDataError("Could not find matching data " + datarev)
			else:
				return commit
		except KeyError:
			raise NoDataError("Could not find matching data " + datarev)

	def find_metadata_commit(self,branchname):
		# Find metadata branch
		branch = self.repo.lookup_branch(branchname)

		if branch is None:
			raise NoMetadataBranchError("Could not find metadata branch in the repository")

		# Find commit in metadata branch
		commit = branch.get_object()

		if not isinstance(commit,pygit2.Commit):
			raise NoMetadataBranchError("Could not find metadata branch with commit in the repository")
		else:
			return commit

	def find_latest_commitid_in_metadata(self,branchname,datacommit):
		try:
			self.debugmsg("branchname: %s, datacommit.id %s" % (branchname,datacommit.id))
			metadatatree = self.repo.revparse_single("%s:%s" % (branchname,datacommit.id))

			if not isinstance(metadatatree,pygit2.Tree):
				raise MetadataTreeNotFoundError("Could not find matching metadata tree")
			else:
				return datacommit.id

		except KeyError:
			if len(datacommit.parent_ids)==1:
				datacommit=self.find_data_commit(datacommit.parent_ids[0].__str__())
				return self.find_latest_commitid_in_metadata(branchname,datacommit)
			elif len(datacommit.parent_ids)>1:
				raise MetadataTreeNotFoundError("Merges not supported")
			else:
				raise MetadataTreeNotFoundError("Could not find matching metadata tree")



	# def get_blob(self,treelist,currenttree):
	# 	nextitem = treelist[0]
	# 	try:
	# 		if len(treelist)==1:
	# 			if len(nextitem)==0:
	# 				raise MetadataRequestError("The request was not valid - check the stream name")
	# 			metadata=currenttree[nextitem]
	# 			metadatablob=self.repo[metadata.id]
	# 			if not isinstance(metadatablob,pygit2.Blob):
	# 				raise MetadataBlobNotFoundError("Could not find metadata blob in the tree")
	# 			return MetadataBlob(metadatablob,nextitem,currenttree)
	# 		else:									# We are not in the right tree so move onto the next tree
	# 			nexttree=currenttree[nextitem]      # Find the sub-tree in the current tree
	# 			nexttreeitem=self.repo[nexttree.id] # Retrieve the tree from the repository using its ID
	# 			if isinstance(nexttreeitem,pygit2.Tree):
	# 				self.debugmsg("Found next tree " + nextitem)
	# 				return self.get_blob(treelist[1:],nexttreeitem)
	# 			else:
	# 				raise MetadataTreeNotFoundError("Could not find metadata with path specified (Tree %s not found)" % nextitem)
	# 	except KeyError, e:
	# 		raise MetadataBlobNotFoundError("No metadata found for " + e.message) # Metadata object does not exist yet

# typedef enum {
# 	GIT_STATUS_CURRENT = 0,
#
# 	GIT_STATUS_INDEX_NEW        = (1u << 0),
# 	GIT_STATUS_INDEX_MODIFIED   = (1u << 1),
# 	GIT_STATUS_INDEX_DELETED    = (1u << 2),
# 	GIT_STATUS_INDEX_RENAMED    = (1u << 3),
# 	GIT_STATUS_INDEX_TYPECHANGE = (1u << 4),
#
# 	GIT_STATUS_WT_NEW           = (1u << 7),
# 	GIT_STATUS_WT_MODIFIED      = (1u << 8),
# 	GIT_STATUS_WT_DELETED       = (1u << 9),
# 	GIT_STATUS_WT_TYPECHANGE    = (1u << 10),
# 	GIT_STATUS_WT_RENAMED       = (1u << 11),
# 	GIT_STATUS_WT_UNREADABLE    = (1u << 12),
#
# 	GIT_STATUS_IGNORED          = (1u << 14),
# 	GIT_STATUS_CONFLICTED       = (1u << 15),
# } git_status_t;

# typedef enum {
# 	GIT_DELTA_UNMODIFIED = 0,  /**< no changes */
# 	GIT_DELTA_ADDED = 1,	   /**< entry does not exist in old version */
# 	GIT_DELTA_DELETED = 2,	   /**< entry does not exist in new version */
# 	GIT_DELTA_MODIFIED = 3,    /**< entry content changed between old and new */
# 	GIT_DELTA_RENAMED = 4,     /**< entry was renamed between old and new */
# 	GIT_DELTA_COPIED = 5,      /**< entry was copied from another old entry */
# 	GIT_DELTA_IGNORED = 6,     /**< entry is ignored item in workdir */
# 	GIT_DELTA_UNTRACKED = 7,   /**< entry is untracked item in workdir */
# 	GIT_DELTA_TYPECHANGE = 8,  /**< type of entry changed between old and new */
# 	GIT_DELTA_UNREADABLE = 9,  /**< entry is unreadable */
# 	GIT_DELTA_CONFLICTED = 10, /**< entry in the index is conflicted */
# } git_delta_t;


	def get_data_path_in_metadata(self,branchname,path):
		metadatadatacommitid = self.find_latest_commitid_in_metadata(branchname,self.datarootcommit)
		datapath = os.path.join(metadatadatacommitid,path,Metadata.data_hash)
		self.debugmsg("data path = " + datapath)
		return datapath

	def get_metadata_blob_path(self,branchname,path,streamname):
		metadatadatacommitid = self.find_latest_commitid_in_metadata(branchname,self.datarootcommit)
		metadatablobpath = os.path.join(metadatadatacommitid.__str__(),path,Metadata.metadata_hash, streamname)
		self.debugmsg("metadata blob path = " + metadatablobpath)
		return metadatablobpath

	def get_new_metadata_blob_path(self,path,streamname):
		metadatablobpath = os.path.join(self.datarootcommit.id.__str__(),path,Metadata.metadata_hash, streamname)
		self.debugmsg("new metadata blob path = " + metadatablobpath)
		return metadatablobpath

	def get_metadata_blob(self,branchname,path,streamname):
		# Find metadata branch
		# metaadatarootcommit = self.find_metadata_commit(branchname)
		# self.metadatatree = self.find_metadata_tree(branchname,self.datacommit)

		metadatablobpath = self.get_metadata_blob_path(branchname,path,streamname)

		# Try to get the blob
		try:
			metadatablob = self.repo.revparse_single("%s:%s" % (branchname,metadatablobpath))
			if not isinstance(metadatablob,pygit2.Blob):
				raise MetadataBlobNotFoundError("Could not find metadata blob in the tree")
		except KeyError,e:
			raise MetadataBlobNotFoundError("Could not find metadata blob in the tree")

		# Try to get the data
		try:
			dataitem = self.repo.revparse_single("%s:%s" % (self.datarev,path))

			# Is it a tree or blob?
			if isinstance(dataitem,pygit2.Tree):
				datachanged = pygit2.GIT_STATUS_CURRENT > 0
			elif isinstance(dataitem,pygit2.Blob):
				f = open(path, 'r')
				diff = dataitem.diff_to_buffer(f.read()) # Returns a Diff
				f.close()

				delta = diff.delta # Get the Delta object
				datachanged = delta.status > 0
			else:
				dataitem = None
				datachanged = False
		except KeyError:
			dataitem = None
			datachanged = False

		# Try to find matching data file
		# try:
		# 	datablobstatus = self.repo.status_file("file.txt")
		# 	print "data blob status: %d" % datablobstatus
		# except KeyError:
		# 	raise MatchingDataBlobNotFoundError

		return MetadataContainer(metadatablob,dataitem,datachanged)
		# return self.get_blob(parentslist,self.commit.tree)

	def write_tree_hierarchy(self,parentslist,branchname,newentryid,ismetadatatree=True,force=False):
		newentry = self.repo[newentryid]

		# Get last entry as name of tree to save (work backwards in tree list)
		newentryname = parentslist[-1]

		# Use remaining entries as the parent tree's path
		# Python does the right thing here for most strings and lists so no need to check the length of parentslist
		newentryparentpath = os.sep.join(parentslist[0:-1])

		self.debugmsg("Looking for %s/%s" % (newentryparentpath , newentryname))

		try:
			tree = self.repo.revparse_single('{0}:{1}'.format(branchname,newentryparentpath))
			if isinstance(tree,pygit2.Tree):
				# Found existing tree so modify it
				treebuilder = self.repo.TreeBuilder(tree)
			else:
				if force:
					# Create new tree
					treebuilder = self.repo.TreeBuilder()
				else:
					raise Exception("Expected Tree, got " + str(type(tree)))

		except KeyError:
			# Tree doesn't exist so create a new one
			treebuilder = self.repo.TreeBuilder()

		# if ismetadatatree:
		# 	dataentry = None
		# else:
		# 	try:
		# 		dataentry = self.repo.revparse_single("HEAD:")


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

		self.debugmsg("Tree containing %s saved with ID %s" % (newentryname, treebuilderid.__str__()))

		# If we're on the last one, len(parentslist) will be 1
		if len(parentslist) > 1:
			# Recurse up the tree, pass modified tree to next call of function
			return self.write_tree_hierarchy(parentslist[0:-1],branchname,treebuilderid,ismetadatatree,force)
		else:
			return treebuilderid

	def save_metadata_blob(self,newfile,branchname,path,streamname,force=False):
		try:
			currentmetadatacommit = self.find_metadata_commit(branchname)
			branch = self.repo.lookup_branch(branchname)
			branchref = branch.name
			commitparentids = [currentmetadatacommit.id]
		except NoMetadataBranchError:
			commitparentids = [ ]
			branchref = 'refs/heads/%s' % branchname

		print commitparentids.__str__()

		# Save the object into the repository
		newblobid = self.repo.create_blob(newfile)

		# Save metadata tree
		parentspath = self.get_new_metadata_blob_path(path,streamname)
		parentslist = parentspath.split(os.sep)
		toptreeid = self.write_tree_hierarchy(parentslist, branchname, newblobid, ismetadatatree=True, force=force)

		# print "Create for %s, %s, %s, %s" % (branchname,path,toptreeid,commitparentids)
		# Create a commit
		commitid = self.repo.create_commit(branchref,
			pygit2.Signature('Mark', 'cms4@soton.ac.uk'),
			pygit2.Signature('Mark', 'cms4@soton.ac.uk'),
			"Updated metadata for " + path,
			toptreeid,
			commitparentids)

		# Update the branch's reference to point to the commit
		# self.branchref.set_target(commitid,pygit2.Signature('Mark', 'cms4@soton.ac.uk'), "Updated metadata")

		self.debugmsg("Commit saved as " + commitid.__str__())

		return commitid

	def check_path_request(self,path):
		"""Work out the path for the metadata request"""

		# If no path was specified, use the default for the repository object
		if path is None:
			path=self.rel_req_path

		# Remove start slash from the request as we start searching from the root anyway
		if os.path.isabs(path):
			path=path[1:]

		return path

	def print_metadata(self,fileaction,branchname,streamname,path=None,keyfilter=None,valuefilter=None):
		path=self.check_path_request(path)

		# Get the metadata
		metadata_container = self.get_metadata_blob(branchname,path,streamname)

		if FileActions.is_action(fileaction,FileActions.json):
			try:
				self.printjson(metadata_container.metadatablob,keyfilter,valuefilter)
			except ValueError:
				if FileActions.is_action(fileaction,FileActions.dump):
					self.dumpfile(metadata_container.metadatablob)
				else:
					raise MetadataFileFormatError("Not JSON data. Use --dump to show file anyway.")
		elif FileActions.is_action(fileaction,FileActions.dump):
			self.dumpfile(metadata_container.metadatablob)

		if metadata_container.datablob is None:
			print TextColor.Red + 'NOTE: Matching data not found' + TextColor.Reset

		if metadata_container.datachanged:
			print TextColor.Red + "NOTE: Data has been modified" + TextColor.Reset

	def printjson(self,gitblob,keyfilter=None,valuefilter=None):
		data = json.loads(gitblob.data)
		for key, value in data.iteritems():
			if (keyfilter is None or keyfilter==key.__str__()) and (valuefilter is None or valuefilter==value.__str__()):
				print '{:<20} {:<20}'.format(key,  value)

	def dumpfile(self,gitblob):
		print gitblob.data

	def update_metadata(self,k,v,branchname,streamname,path=None,force=False):

		path=self.check_path_request(path)

		try:
			# Get the metadata
			metadatablob = self.get_metadata_blob(branchname,path,streamname)
			jsondict = json.loads(metadatablob.metadatablob.data)
		except (MetadataBlobNotFoundError, MetadataTreeNotFoundError):
			jsondict = json.loads("{}")

		# Update dictionary
		jsondict[k] = v

		# Create an object to save in the repository
		newfile = json.dumps(jsondict)

		commitid = self.save_metadata_blob(newfile,branchname,path,streamname,force)

		# self.save_metadata(blobdata,path)
