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


class MetadataRepository(pygit2.Repository):

	# We're just looking for a
	# data_name = hashlib.md5('data').hexdigest()
	# metadata_name = hashlib.md5('metadata').hexdigest()
	data_name = uuid.uuid5(uuid.NAMESPACE_X500, 'data').__str__()
	metadata_name = uuid.uuid5(uuid.NAMESPACE_X500, 'metadata').__str__()

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

	def list_metadata_in_stream(self, datarev, streamname, path=None):
		# Get the path or generate it if not specified
		path = self.check_path_request(path)
		normpath = os.path.normpath(path)

		print "\n* Listing metadata for file path: '{}'\n* Data branch specified: '{}'".format(normpath, datarev)

		# Find path of metadata node
		metadatanodepath = self.get_metadata_node_path(path, streamname)

		# Find metadata branch
		metaadatacommit = self.find_metadata_commit(self.metadataref)

		# Retrieve metadata node
		try:
			metadatanode = self.revparse_single("%s:%s" % (metaadatacommit.id, metadatanodepath))
			if not isinstance(metadatanode, pygit2.Tree):
				raise MetadataBlobNotFoundError("Could not find metadata blob in the tree")
		except KeyError:
			raise MetadataBlobNotFoundError("Could not find metadata blob in the tree")

		# Retrieve the item that the user wants us to list metadata for
		if datarev is None:
			if os.path.isfile(path):
				requesteddataistree = False
				requestedblobid = pygit2.hashfile(path)
				if requestedblobid in self:
					dataitem = self[requestedblobid]
					requesteddataexists = True
					print "* Blob specified has ID of %s" % requestedblobid
				else:
					requesteddataexists = False
			elif os.path.isdir(normpath):
				# set a tree
				requesteddataistree = True
				requesteddataexists = True
				print "* Looking for directory %s" % normpath
			else:
				requesteddataexists = False
		else:
			try:
				dataitem = self.revparse_single("%s:%s" % (datarev, path))
				dataitemcommit = self.revparse_single("%s" % datarev)
				dataitemcommitparents = [commit.id.__str__() for commit in self.walk(dataitemcommit.id, pygit2.GIT_SORT_REVERSE)]
				self.debugmsg("parent commits %s " % dataitemcommitparents)
				requesteddataexists = True

				# Check what the item is (file or directory)
				if isinstance(dataitem, pygit2.Blob):
					requesteddataistree = False
					print "* Looking for metadata for blob %s" % dataitem.id
				elif isinstance(dataitem, pygit2.Tree):
					requesteddataistree = True
					print "* Looking for metadata for directory '%s' " % path
				else:
					requesteddataexists = False
					MetadataRepository.errormsg("Data requested does not exist")

			except KeyError:
				requesteddataexists = False
				MetadataRepository.errormsg("Data requested does not exist")

		# Print details of all of the matching metadata (looking up the matching data commit)
		print
		outputformatstr = "{:41s}{:41s}{:16s}{:12}{}"
		print outputformatstr.format("Data commit ID containing metadata", "Data in commit", "Data matches", "Inheritable", "Committed")
		print outputformatstr.format("-------------------------", "--------------", "------------", "-----------", "---------")

		# Iterate around each metadata item defined
		for metadataentry in metadatanode:

			# Set some default values
			dataitemmatchesrequest = False
			matchingdataidstr = "Matching data could not be found"
			matchingdatacommitstr = "Matching data could not be found"
			metadatainheritable = False

			# Attempt to find data commit that metadata pertains to
			try:
				matchingdatacommitid = metadataentry.name
				matchingdatacommit = self[matchingdatacommitid]

				# Attempt to find data item matching path
				matchingdataitem = self.revparse_single("%s:%s" % (matchingdatacommitid, path))

				if requesteddataexists:
					matchingdatacommitstr = datetime.datetime.fromtimestamp(matchingdatacommit.commit_time)
					if datarev is not None:
						metadatainheritable = metadataentry.name in dataitemcommitparents

					if requesteddataistree:
						dataitemmatchesrequest = isinstance(matchingdataitem, pygit2.Tree)
						matchingdataidstr = path
					else:
						dataitemmatchesrequest = (matchingdataitem.id == dataitem.id)
						matchingdataidstr = matchingdataitem.id

			except KeyError:
				pass

			matchingdatastr = ("YES" if dataitemmatchesrequest else "NO")
			metadatainheritablestr = ("YES" if metadatainheritable else "NO")

			print outputformatstr.format(matchingdatacommitid, matchingdataidstr, matchingdatastr, metadatainheritablestr, matchingdatacommitstr)

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

	def update_metadata(self, k, v, streamname, datarev, path=None, force=False):
		path = self.check_path_request(path)

		# Get the data commit
		datacommitwithobject = self.find_data_commit_with_object(datarev, path)

		datacommitwithobjectid = datacommitwithobject.id.__str__()

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

	def print_metadata(self, streamname, datarev, path=None, fileaction=FileActions.dump, keyfilter=None, valuefilter=None):
		path = self.check_path_request(path)

		# Get the data commit
		datacommitwithobject = self.find_data_commit_with_object(datarev, path)

		datacommitwithobjectid = datacommitwithobject.id.__str__()

		# Get the metadata
		metadata_container = self.get_metadata_blob(streamname, datacommitwithobjectid, path=path)

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
