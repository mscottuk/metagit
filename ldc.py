import os
import json
import pygit2
import sys
import uuid
import datetime

class NoRepositoryError(Exception):
	"""Could not find a Git repository"""
	pass


class MetadataCommitNotFoundError(Exception):
	"""Could not find a metadata tree"""
	pass


class NoMetadataBranchError(Exception):
	"""Could not find a metadata branch in the repository"""
	pass


class MetadataBlobNotFoundError(Exception):
	"""Could not find metadata blob in the tree"""
	pass


class DataBlobNotFoundError(Exception):
	"Could not find data blob in repository"
	pass


class NoDataError(Exception):
	"""Could not find matching data"""
	pass


class MetadataWriteError(Exception):
	"""The metadata could not be written"""
	pass


class MetadataReadError(Exception):
	"""The metadata could not be read"""
	pass


class MetadataFileFormatError(Exception):
	"""File is not in correct format"""
	pass


class ParameterError(Exception):
	"""Parameters not passed correctly"""
	pass


class MetadataInvalidError(Exception):
	"""Metadata does not match request"""  # e.g. An uncommitted file
	pass


class TextColor:
	Red = '\033[31m'
	Reset = '\033[0m'


class FileActions:
	dump = 1
	json = 2
	default = dump | json

	@staticmethod
	def is_action(action, actioncmp):
		return action & actioncmp == actioncmp


class DataRevisionMetadataSearchMethod:
	SearchBackForEarlierMetadataAllowed = 1  # FindAndUpdateEarlierMetadata
	UseRevisionSpecifiedOnly = 2             # CreateNewMetadata


class MetadataRepository(pygit2.Repository):

	# We're just looking for a
	# data_name = hashlib.md5('data').hexdigest()
	# metadata_name = hashlib.md5('metadata').hexdigest()
	data_name = uuid.uuid5(uuid.NAMESPACE_X500, 'data').__str__()
	metadata_name = uuid.uuid5(uuid.NAMESPACE_X500, 'metadata').__str__()
	datarev_default_get = "HEAD"

	# We need two things to find the metadata:
	# 1 - A path to the file
	# 2 - A reference to a git commit for the metadata
	def __init__(self, req_path, metadataref, discover=True, debug=False):

		# Sort out paths
		self.req_path = req_path
		self.abs_req_path = os.path.abspath(req_path)
		self.repo_path = self.find_repository_path(self.abs_req_path, discover)
		self.base_path = os.path.dirname(self.repo_path)
		self.rel_req_path = self.abs_req_path[len(self.base_path) + 1:]

		# Initialise repository
		pygit2.Repository.__init__(self, self.repo_path)

		# Save metadataref
		self.metadataref = metadataref

		# Save miscellaneous arguments
		self.discover = discover
		self.debug = debug

		# Print debug info
		self.debugmsg("Repo=" + self.repo_path)
		self.debugmsg("Abs=" + self.abs_req_path)
		self.debugmsg("Rel=" + self.rel_req_path)

	@staticmethod
	def errormsg(msg):
		sys.stderr.write("%s\n" % msg)

	def debugmsg(self, msg):
		if self.debug:
			MetadataRepository.errormsg(msg)

	def find_repository_path(self, abs_req_path, discover):
		repo_search_path = abs_req_path
		found = False

		# If we have been asked to search for a repository use discover_repository()
		if discover:
			while not found:
				try:
					repo_path = os.path.abspath(pygit2.discover_repository(repo_search_path))
					found = True

				# Repository could not be found, so start looking for a repository higher up
				# discover_repository() only does this if the folder exists
				except KeyError:
					# Break if we have a blank string or have reached the root directory
					if repo_search_path in ["", os.path.abspath(os.sep)]:
						break
					# Otherwise, carry on looking up the tree
					else:
						repo_search_path = os.path.dirname(repo_search_path)

		# Otherwise just use the path given (which will raise an unhandled exception if it doesn't exist)
		else:
			repo_path = abs_req_path
			found = True

		if found:
			return repo_path
		else:
			raise NoRepositoryError("Could not find a Git repository")

	def find_data_commit(self, datarev):
		try:
			commit = self.revparse_single(datarev)
			if not isinstance(commit, pygit2.Commit):
				raise NoDataError("Could not find matching data " + datarev)
			else:
				return commit
		except KeyError:
			raise NoDataError("Could not find matching data " + datarev)

	def find_metadata_commit(self, metadataref):
		try:
			metadatacommit = self.revparse_single(metadataref)
			if not isinstance(metadatacommit, pygit2.Commit):
				raise MetadataCommitNotFoundError("Expected Commit for reference %s" % metadataref)
			else:
				return metadatacommit
		except KeyError:
			raise NoMetadataBranchError("No metadata could be found")

	def check_path_request(self, path):
		"""Work out the path for the metadata request"""

		# If no path was specified, use the default for the repository object
		if path is None:
			path = self.rel_req_path

		# Remove start slash from the request as we start searching from the root anyway
		if os.path.isabs(path):
			path = path[1:]

		return path

	def get_metadata_node_path(self, path, streamname):
		metadatanodepath = os.path.join(path, MetadataRepository.metadata_name, streamname)
		self.debugmsg("metadata node path = " + metadatanodepath)
		return metadatanodepath

	def get_metadata_blob_path(self, path, streamname, datacommitid):
		# metadatadatacommitid = self.find_latest_commitid_in_metadata(branchname, self.datarootcommit)
		metadatanodepath = self.get_metadata_node_path(path, streamname)
		metadatablobpath = os.path.join(metadatanodepath, datacommitid)
		self.debugmsg("metadata blob path = " + metadatablobpath)
		return metadatablobpath

	def get_metadata_blob(self, streamname, datarev, path=None):
		path = self.check_path_request(path)

		# Find metadata branch
		metaadatacommit = self.find_metadata_commit(self.metadataref)

		# Find the data commit
		datacommitid = self.find_data_commit(datarev).id.__str__()

		# Generate the path from the object requested, stream name and revision
		metadatablobpath = self.get_metadata_blob_path(path, streamname, datacommitid)

		# Try to get the blob
		try:
			metadatablob = self.revparse_single("%s:%s" % (metaadatacommit.id, metadatablobpath))
			if not isinstance(metadatablob, pygit2.Blob):
				raise MetadataBlobNotFoundError("Could not find metadata blob in the tree")
			else:
				return metadatablob
		except KeyError:
			raise MetadataBlobNotFoundError("Could not find metadata blob in the tree")

	def get_metadata_node(self, streamname, path):
		# Find metadata branch
		metaadatacommit = self.find_metadata_commit(self.metadataref)

		# Find path of metadata node
		metadatanodepath = self.get_metadata_node_path(path, streamname)

		# Retrieve metadata node
		try:
			metadatanode = self.revparse_single("%s:%s" % (metaadatacommit.id, metadatanodepath))
			if not isinstance(metadatanode, pygit2.Tree):
				raise MetadataBlobNotFoundError("Could not find metadata blob in the tree")
			else:
				return metadatanode
		except KeyError:
			raise MetadataBlobNotFoundError("Could not find metadata blob in the tree")

	def find_fs_blob_in_repository(self, path):
		if os.path.isfile(path):
			requestedblobid = pygit2.hashfile(path)  # Find the ID of the file so we can check if it's in repository
			if (requestedblobid in self):            # Check if the file is in the repository
				dataitem = self[requestedblobid]     # We found the file so save it for later
				return dataitem

		# If we reach here, it is a directory or it was not found on the file system
		raise DataBlobNotFoundError("Could not find data blob in repository")

	def find_path_in_repository(self, datarev, path):
		normpath = os.path.normpath(path)

		# Retrieve the item that the user wants us to list metadata for
		if datarev is None:
			# User did not specify a revision so we have to look on the file system
			try:
				# Without a data revision, we can only lookup a blob in the repository
				dataitem = self.find_fs_blob_in_repository(path)
				print "* Blob specified has ID of %s" % dataitem.id
				return dataitem
			except DataBlobNotFoundError:
				if os.path.isdir(normpath):
					# Path is a directory so can't return a repository item
					print "* Looking for directory %s" % normpath
					return None
				else:
					# Path doesn't exist at all
					return None
		else:
			# We have a data revision so find the data in the repository
			try:
				dataitem = self.revparse_single("%s:%s" % (datarev, path))

				# Check what the item is (file or directory)
				if isinstance(dataitem, pygit2.Blob):
					print "* Looking for metadata for blob %s" % dataitem.id
					return dataitem
				elif isinstance(dataitem, pygit2.Tree):
					print "* Looking for metadata for directory '%s' " % normpath
					return dataitem
				else:
					MetadataRepository.errormsg("Data requested does not exist")
					return None

			except KeyError:
				MetadataRepository.errormsg("Data requested does not exist")
				return None

	def list_metadata_in_stream(self, datarev, streamname, path=None):
		# Get the path or generate it if not specified
		path = self.check_path_request(path)
		normpath = os.path.normpath(path)

		print "\n* Listing metadata for file path: '{}'\n* Data branch specified: '{}'\n* Stream specified: {}".format(normpath, datarev, streamname)

		if datarev is not None:
			dataitemcommit = self.revparse_single("%s" % datarev)
			dataitemcommitparents = [commit.id.__str__() for commit in self.walk(dataitemcommit.id, pygit2.GIT_SORT_REVERSE)]
			self.debugmsg("parent commits %s " % dataitemcommitparents)

		outputformatstr = "{:40} {:40} {:15} {:11} {!s:19}"

		# Retrieve the data item requested
		dataitemrequested = self.find_path_in_repository(datarev, path)

		# Retrieve metadata node for the given path
		metadatanode = self.get_metadata_node(streamname, path)

		matchingstrings = []
		notmatchingstrings = []

		# Iterate around each metadata item defined for the given path
		for datacommitwithmetadataid in [metadataentry.name for metadataentry in metadatanode]:

			if dataitemrequested is None:
				datacommitwithmetadatastr = "Matching data could not be found"
				dataitemmatchesrequest = False
				matchingdataidstr = "Matching data could not be found"
			else:
				try:
					# Attempt to find data commit that metadata pertains to
					datacommitwithmetadata = self.find_data_commit(datacommitwithmetadataid)
					datacommitwithmetadatastr = datetime.datetime.fromtimestamp(datacommitwithmetadata.commit_time)

					# Attempt to find data item matching path
					matchingdataitem = self.revparse_single("%s:%s" % (datacommitwithmetadataid, path))

					if isinstance(dataitemrequested, pygit2.Tree):
						dataitemmatchesrequest = isinstance(matchingdataitem, pygit2.Tree)
						matchingdataidstr = "Path '%s'" % normpath
					else:
						dataitemmatchesrequest = (matchingdataitem.id == dataitemrequested.id)
						matchingdataidstr = matchingdataitem.id

				except (NoDataError, KeyError):
					# Data could not be found
					datacommitwithmetadatastr = "Matching data could not be found"
					matchingdataidstr = "Matching data could not be found"
					dataitemmatchesrequest = False

			metadatainheritable = (dataitemrequested is not None) and (datarev is not None) and (datacommitwithmetadataid in dataitemcommitparents) and (dataitemmatchesrequest)
			metadatainheritablestr = ("YES" if metadatainheritable else "NO")
			matchingdatastr = ("YES" if dataitemmatchesrequest else "NO")

			# if datarev is None or (dataitemmatchesrequest and metadatainheritable):
			outputstring = outputformatstr.format(datacommitwithmetadataid, matchingdataidstr, matchingdatastr, metadatainheritablestr, datacommitwithmetadatastr)
			if ((dataitemrequested is not None) or (datarev is None)) and dataitemmatchesrequest:
				matchingstrings.append(outputstring)
			else:
				notmatchingstrings.append(outputstring)

		print
		print outputformatstr.format("=" * 40, "=" * 40, "=" * 15, "=" * 11, "=" * 19)
		print outputformatstr.format("Data commit ID containing metadata", "Data in commit", "Data matches", "Inheritable", "Committed")
		print outputformatstr.format("-" * 40, "-" * 40, "-" * 15, "-" * 11, "-" * 19)

		if len(matchingstrings) > 0:
			# Print details of all of the matching metadata (looking up the matching data commit)
			print "Found the following matches:"
			print "\n".join(matchingstrings)
		else:
			print "None found"

		# print
		# print outputformatstr.format("Data commit ID containing metadata", "Data in commit", "Data matches", "Inheritable", "Committed")
		# print outputformatstr.format("-" * 40, "-" * 40, "-" * 15, "-" * 11, "-" * 19)

		print outputformatstr.format("-" * 40, "-" * 40, "-" * 15, "-" * 11, "-" * 19)
		print "Other versions of metadata for same path:"
		if len(notmatchingstrings) > 0:
			print "\n".join(notmatchingstrings)
		else:
			print "None found"

		print outputformatstr.format("=" * 40, "=" * 40, "=" * 15, "=" * 11, "=" * 19)
		print

	def write_tree_hierarchy(self, parentslist, newentryid, force=False):
		newentry = self[newentryid]

		# Get last entry as name of tree to save (work backwards in tree list)
		newentryname = parentslist[-1]

		# Use remaining entries as the parent tree's path
		# Python does the right thing here for most strings and lists so no need to check the length of parentslist
		newentryparentpath = os.sep.join(parentslist[0:-1])

		self.debugmsg("Looking for %s/%s" % (newentryparentpath, newentryname))

		try:
			tree = self.revparse_single('{0}:{1}'.format(self.metadataref, newentryparentpath))
			if isinstance(tree, pygit2.Tree):
				# Found existing tree so modify it
				treebuilder = self.TreeBuilder(tree)
			else:
				# Didn't find a try so check if we are allowed to overwrite it
				if force:
					# Create new tree
					treebuilder = self.TreeBuilder()
				else:
					raise Exception("Expected Tree, got " + str(type(tree)))

		except KeyError:
			# Tree doesn't exist so create a new one
			treebuilder = self.TreeBuilder()

		if isinstance(newentry, pygit2.Blob):
			self.debugmsg("Writing blob")
			# Create a new tree with the blob in it, editing the last tree in the path if it exists.
			treebuilder.insert(newentryname, newentry.id, pygit2.GIT_FILEMODE_BLOB)
		elif isinstance(newentry, pygit2.Tree):
			self.debugmsg("Writing tree")
			# Create a new tree which points to the blob's tree, editing the last but one tree in the path if it exists.
			treebuilder.insert(newentryname, newentry.id, pygit2.GIT_FILEMODE_TREE)
		else:
			raise Exception("Expected Blob or Tree, got " + str(type(newentry)))

		treebuilderid = treebuilder.write()

		self.debugmsg("Tree containing %s saved with ID %s" % (newentryname, treebuilderid.__str__()))

		# If we're on the last one, len(parentslist) will be 1
		if len(parentslist) > 1:
			# Recurse up the tree, pass modified tree to next call of function
			return self.write_tree_hierarchy(parentslist[0:-1], treebuilderid, force)
		else:
			return treebuilderid

	def save_metadata_blob(self, newfile, streamname, datarev, path=None, force=False):
		path = self.check_path_request(path)

		# Branch might not exist yet, so try to find the metadata branch,
		# otherwise create a new one
		try:
			# Find metadata branch
			currentmetadatacommit = self.find_metadata_commit(self.metadataref)
			metadatareftoupdate = self.metadataref
			commitparentids = [currentmetadatacommit.id]

		# metadataref does not exist yet
		except NoMetadataBranchError:
			# There is no reference to update so create the commit without a reference
			metadatareftoupdate = None
			commitparentids = []

		# Save the object into the repository
		newblobid = self.create_blob(newfile)

		# Find the data commit
		datacommitid = self.find_data_commit(datarev).id.__str__()

		# Save metadata tree
		parentspath = self.get_metadata_blob_path(path, streamname, datacommitid)
		parentslist = parentspath.split(os.sep)
		toptreeid = self.write_tree_hierarchy(parentslist, newblobid, force=force)

		# Create a commit
		commitid = self.create_commit(
			metadatareftoupdate,
			pygit2.Signature('Mark', 'cms4@soton.ac.uk'),
			pygit2.Signature('Mark', 'cms4@soton.ac.uk'),
			"Updated metadata for " + path,
			toptreeid,
			commitparentids)

		if metadatareftoupdate is None:
			head_ref = self.create_reference(self.metadataref, commitid)

		self.debugmsg("Commit %s created." % (commitid))
		print "Metadata for '%s (%s)' saved to stream '%s' in '%s'." % (path, datacommitid, streamname, self.metadataref)

		return commitid

	def find_first_data_commit_with_tree(self, treepath, currentcommit):
		if len(currentcommit.parents) > 1:
			raise MetadataReadError("Merges not supported")
		elif len(currentcommit.parents) == 0:
			# No parent so current commit is the first to contain this tree
			return currentcommit
		else:
			parentcommit = currentcommit.parents[0]

			try:
				treefound = self.revparse_single("%s:%s" % (parentcommit.id, treepath))
				if not isinstance(treefound, pygit2.Tree):
					# Tree was updated (it used to be a blob)
					return currentcommit
				else:
					# Try next one
					return self.find_first_data_commit_with_tree(treepath, parentcommit)
			except KeyError:
				# Tree could not be found
				return currentcommit

	# def find_first_data_commit_with_tree(self, treepath, treeid, currentcommit):
	# 	# DO WE REALLY LOSE THE METADATA WHEN THE CONTENTS OF THE DIRECTORY CHANGE?
	# 	# PERHAPS USING THE PATH RATHER THAN THE TREEID IS BETTER?
	# 	if len(currentcommit.parents) > 1:
	# 		raise MetadataReadError("Merges not supported")
	# 	elif len(currentcommit.parents) == 0:
	# 		# No parent so current commit is the first to contain this tree
	# 		return currentcommit
	# 	else:
	# 		parentcommit = currentcommit.parents[0]
	#
	# 		try:
	# 			treefound = self.revparse_single("%s:%s" % (parentcommit, treepath))
	# 			if not isinstance(treefound, pygit2.Tree):
	# 				# Tree was updated (it used to be a blob)
	# 				return currentcommit
	# 			if treefound.id == treeid:
	# 				# Try next one
	# 				return self.find_first_data_commit_with_tree(treepath, parentcommit)
	# 			else:
	# 				# Tree was updated
	# 				return currentcommit
	# 		except KeyError:
	# 			# Tree could not be found
	# 			return currentcommit

	def find_first_data_commit_with_blob(self, dataobject, currentcommit):
		currenttree = currentcommit.tree

		self.debugmsg("looking for %s in %s" % (dataobject.id, currentcommit.id))

		if len(currentcommit.parents) > 1:
			raise MetadataReadError("Merges not supported")
		elif len(currentcommit.parents) == 1:
			# Compare against the commit's parent
			parentcommit = currentcommit.parents[0]
			parenttree = parentcommit.tree
			diff = currenttree.diff_to_tree(parenttree, swap=True)
		else:
			# No parent commit to compare against so we will see what has been added in the first commit
			parentcommit = None
			parenttree = None
			diff = currenttree.diff_to_tree(swap=True)

		# Check each change in the diff to see if we can find where our object was added
		for patch in diff:
			delta = patch.delta
			if (delta.new_file.id == dataobject.id) \
				and (delta.status & pygit2.GIT_DELTA_ADDED == pygit2.GIT_DELTA_ADDED):
				return currentcommit

		# Could not find the blob so check the next commit
		if parentcommit is not None:
			return self.find_first_data_commit_with_blob(dataobject, parentcommit)
		else:
			return None

	def find_data_commit_with_object(self, datarev, path):
		datacommit = self.revparse_single(datarev)
		if not isinstance(datacommit, pygit2.Commit):
			raise NoDataError("Data commit does not exist")

		try:
			objectatpath = self.revparse_single("%s:%s" % (datarev, path))
		except KeyError:
			raise NoDataError("Data does not exist in commit")

		if isinstance(objectatpath, pygit2.Blob):
			datacommitwithobject = self.find_first_data_commit_with_blob(objectatpath, datacommit)
		elif isinstance(objectatpath, pygit2.Tree):
			datacommitwithobject = self.find_first_data_commit_with_tree(path, datacommit)
		else:
			raise NoDataError("Data does not exist in commit")

		if datacommitwithobject is None:
			raise NoDataError("Data does not exist in repository")

		return datacommitwithobject

	def generate_datarev(self, path):
		normpath = os.path.normpath(path)
		datarev = self.datarev_default_get
		MetadataRepository.errormsg("NOTE: Data revision not specified. Assuming '{}'.".format(datarev))

		if os.path.isfile(normpath):
			# Check what the status of the file is
			status = self.status_file(path)

			if status > pygit2.GIT_STATUS_CURRENT:
				raise MetadataInvalidError("File has been modified but not committed so this metadata is not valid. Use '{}:{}' syntax to see metadata.".format(datarev, path))
		elif os.path.isdir(normpath):
			# Try to find the directory in the revision specified
			try:
				expectedtree = self.revparse_single('%s:%s' % (datarev, path))
				if not isinstance(expectedtree, pygit2.Tree):
					raise ParameterError("Path does not exist and data revision not specified")
			except KeyError:
				raise ParameterError("Path does not exist and data revision not specified")
		else:
			# If it wasn't a file or a directory, report an error
			raise ParameterError("Path does not exist and data revision not specified")

		# If we get here then the file or folder exists in the HEAD commit
		return datarev

	def update_metadata(self, k, v, streamname, datarev, datarevupdatemethod, path=None, force=False):
		path = self.check_path_request(path)

		# Check the data revision supplied.
		# If the user specified None, we need to find the latest metadata for this path and ensure the
		# data hash matches (otherwise it's not committed).
		# What happens if it is a new version of the file that has been committed but has no metadata yet?
		# ...we don't know whether to update earlier commit or update specified commit.
		# ---> So, a set command must always specify the behaviour otherwise unexpected things might happen.
		if datarev is None:
			datarev = self.generate_datarev(path)
			# If we get here then the file or folder exists in the HEAD commit

		# Find the data commit
		if datarevupdatemethod == DataRevisionMetadataSearchMethod.SearchBackForEarlierMetadataAllowed:
			datacommitwithobject = self.find_data_commit_with_object(datarev, path)
		elif datarevupdatemethod == DataRevisionMetadataSearchMethod.UseRevisionSpecifiedOnly:
			datacommitwithobject = self.find_data_commit(datarev)
		else:
			raise ParameterError("Data revision update method required")

		datacommitwithobjectid = datacommitwithobject.id.__str__()

		MetadataRepository.errormsg("'{}' has been found in data commit {}".format(path, datacommitwithobjectid))
		metadatablobpath = self.get_metadata_blob_path(path, streamname, datacommitwithobjectid)
		MetadataRepository.errormsg("Metadata will be updated at path %s" % metadatablobpath)

		try:
			# Get the metadata
			metadatablob = self.get_metadata_blob(streamname, datacommitwithobjectid, path=path)
			jsondict = json.loads(metadatablob.data)
		except (MetadataBlobNotFoundError, NoMetadataBranchError):
			jsondict = json.loads("{}")

		# Update dictionary
		jsondict[k] = v

		# Create an object to save in the repository
		newfile = json.dumps(jsondict)

		commitid = self.save_metadata_blob(newfile, streamname, datacommitwithobjectid, path=path, force=force)

	def copy_metadata(self, sourcestreamname, sourcedatarev, deststreamname, destdatarev, sourcepath, destpath, datarevupdatemethod, force=False):

		# Check the data revision supplied.
		# If the user specified None, we need to find the latest metadata for this path and ensure the
		# data hash matches (otherwise it's not committed).
		# What happens if it is a new version of the file that has been committed but has no metadata yet?
		# ...we don't know whether to update earlier commit or update specified commit.
		# ---> So, a set command must always specify the behaviour otherwise unexpected things might happen.
		if sourcedatarev is None or destdatarev is None or sourcepath is None or destpath is None:
			raise ParameterError("Source datarev and dest datarev must be specified for copy")

		# Find the data commit
		if datarevupdatemethod == DataRevisionMetadataSearchMethod.SearchBackForEarlierMetadataAllowed:
			sourcedatacommitwithobject = self.find_data_commit_with_object(sourcedatarev, sourcepath)
			destdatacommitwithobject = self.find_data_commit_with_object(destdatarev, destpath)
		elif datarevupdatemethod == DataRevisionMetadataSearchMethod.UseRevisionSpecifiedOnly:
			sourcedatacommitwithobject = self.find_data_commit(sourcedatarev)
			destdatacommitwithobject = self.find_data_commit(destdatarev)
		else:
			raise ParameterError("Data revision update method required")

		sourcedatacommitwithobjectid = sourcedatacommitwithobject.id.__str__()
		destdatacommitwithobjectid = destdatacommitwithobject.id.__str__()

		MetadataRepository.errormsg("'{}' has been found in data commit {}".format(sourcepath, sourcedatacommitwithobjectid))
		sourcemetadatablobpath = self.get_metadata_blob_path(sourcepath, sourcestreamname, sourcedatacommitwithobjectid)
		destmetadatablobpath = self.get_metadata_blob_path(destpath, deststreamname, destdatacommitwithobjectid)
		MetadataRepository.errormsg("Metadata will be copied from '{}' to '{}'".format(sourcemetadatablobpath, destmetadatablobpath))

		# Get the metadata, not handling any exceptions if the blob is not found
		sourcemetadatablob = self.get_metadata_blob(sourcestreamname, sourcedatacommitwithobjectid, path=sourcepath)

		newcommitid = self.save_metadata_blob(sourcemetadatablob, deststreamname, destdatacommitwithobjectid, path=destpath, force=force)

	def print_metadata(self, streamname, datarev, datarevgetmethod, path=None, fileaction=FileActions.dump, keyfilter=None, valuefilter=None):
		path = self.check_path_request(path)

		# Please note that if we set the datarev to the new default of HEAD, to know whether
		# data has changed between the metadata's commit, we need to know the
		# requested data and the metadata's actual data commit. For example, if the user specified None:file1
		# then we will look up metadata in HEAD:file1.txt, we will need to check whether file1.txt
		# has changed in the working directory because the user did not explicitly specify HEAD:file1.txt.
		# However, if the user did specify HEAD:file1.txt we can then lookup the metadata for that
		# version of the file.

		if datarev is None:
			datarev = self.generate_datarev(path)
			# If we get here then the file or folder exists in the HEAD commit

		try:
			metadata_container = self.get_metadata_blob(streamname, datarev, path=path)
		except MetadataBlobNotFoundError:
			if datarevgetmethod == DataRevisionMetadataSearchMethod.SearchBackForEarlierMetadataAllowed:
				# Get the data commit
				datacommitwithobject = self.find_data_commit_with_object(datarev, path)
				datacommitwithobjectid = datacommitwithobject.id.__str__()

				# Get the metadata
				metadata_container = self.get_metadata_blob(streamname, datacommitwithobjectid, path=path)
			else:
				raise

		if FileActions.is_action(fileaction, FileActions.json):
			try:
				self.printjson(metadata_container, keyfilter, valuefilter)
			except ValueError:
				if FileActions.is_action(fileaction, FileActions.dump):
					self.dumpfile(metadata_container.metadatablob)
				else:
					raise MetadataFileFormatError("Not JSON data. Use --dump to show file anyway.")
		elif FileActions.is_action(fileaction, FileActions.dump):
			self.dumpfile(metadata_container)

		# if metadata_container.datablob is None:
		# 	print TextColor.Red + 'NOTE: Matching data not found' + TextColor.Reset
		#
		# if metadata_container.datachanged:
		# 	print TextColor.Red + "NOTE: Data has been modified" + TextColor.Reset

	def printjson(self, gitblob, keyfilter=None, valuefilter=None):
		data = json.loads(gitblob.data)
		for key, value in data.iteritems():
			if (keyfilter is None or keyfilter == key.__str__()) and (valuefilter is None or valuefilter == value.__str__()):
				print '{:<20} {:<20}'.format(key, value)

	def dumpfile(self, gitblob):
		print gitblob.data
