import os
import json
import pygit2
import sys
import uuid
import datetime
import re

class NoRepositoryError(Exception):
	"""Could not find a Git repository"""
	pass


class MetadataCommitNotFoundError(Exception):
	"""Could not find a metadata tree"""
	pass


class NoMetadataBranchError(Exception):
	"""Could not find a metadata branch in the repository"""
	pass
	

class RepositoryNotSupported(Exception):
	"""Bare repositories not supported"""
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
	NoSearch = 0
	SearchBackForEarlierMetadataAllowed = 1  # FindAndUpdateEarlierMetadata
	UseRevisionSpecifiedOnly = 2             # CreateNewMetadata

# Parses path strings with the format 's+[REV]:path[:stream]'.
# Accepts arguments: the path, whether the search is required,
# a default base path for a relative path (otherwise defaults to current dir)
# and an optinal repo to use to generate a relative path to the metadata
class MetadataPath:
	datarev_default = None
	datarev_default_get = "HEAD"
	stream_default = "metadata"
	path_syntax = "datarev:metadatapath[:stream]"

	# Passing a repo in means relative paths are generated by combining the base path
	# with the relative path and then calculating a new relative path from the 
	# repo's working directory
	# Not passing a repo in means relative paths are resolved to base path (defaults to os.getcwd())
	# and an absolute path is returned
	def __init__(self, path, path_requires_search=True, base_path=None, repo=None):

		if repo and not isinstance(repo, MetadataRepository):
			raise ParameterError("Please pass a MetadataRepository object")
		
		regexsearch = r'^(?:s(?:earch)?([-\+]))?'

		# Try branch:dir:metadata or branch:dir:'' first
		regex = regexsearch + r'([^:\r\n]*):([^:\r\n]*):?([^:\r\n]*)$'
		path_split = re.match(regex, path)

		# Next, if that didn't work, try just matching dir
		if path_split is None:
			regex = regexsearch + r'():?([^:\r\n]*)()$'
			path_split = re.match(regex, path)

		# Wrong format received - possibly too many ':'s in string
		if path_split is None:

			# Work out whether we need to look for s+/search+ and s-/search- at start of string
			path_syntax = (path_requires_search and '(s+|s-)' or '') + MetadataPath.path_syntax
			
			# Raise exception containing correct syntax
			raise ParameterError("Could not parse '%s'. Please use syntax %s." % (path, path_syntax))

		searching = path_split.group(1)
		self.datarev = path_split.group(2) or MetadataPath.datarev_default
		self.metadatapath = path_split.group(3) or os.getcwd()
		self.streamname = path_split.group(4) or MetadataPath.stream_default

		if path_requires_search:
			if searching == "+":
				self.datarevsearchmethod = DataRevisionMetadataSearchMethod.SearchBackForEarlierMetadataAllowed
			elif searching == "-":
				self.datarevsearchmethod = DataRevisionMetadataSearchMethod.UseRevisionSpecifiedOnly
			else:
				raise ParameterError("Please specify 's+' or 's-'")
		else:
			self.datarevsearchmethod = DataRevisionMetadataSearchMethod.NoSearch

			if searching is not None:
				MetadataRepository.errormsg("Search method will be ignored")

		# Sanitise metadatapath
		self.metadatapath = os.path.normpath(self.metadatapath)

		if base_path and not os.path.isabs(base_path):
			raise ParameterError("Base path needs to be absolute")

		# Generate the absolute path to the passed path
		if not os.path.isabs(self.metadatapath):
			self.metadatapath = os.path.join(base_path or os.getcwd(), self.metadatapath)
			self.metadatapath = os.path.normpath(self.metadatapath)
			print "Using %s for base path" % (base_path and base_path or "current directory")
		
		# Check if the path is within the repository
		if repo:
			regex = r'^' + re.escape(repo.workdir.rstrip(os.sep)) + re.escape(os.sep) + '?(.*)$'
			relmatch = re.match(regex, self.metadatapath)
			if relmatch:
				self.metadatapath = relmatch.group(1)
				self.repo = repo
			else:
				raise ParameterError("Absolute path not within repository")
		else:
			self.repo = None

		MetadataRepository.errormsg( "datarev:" + (self.datarev or "NONE"))
		MetadataRepository.errormsg( "datarevsearchmethod: %s" % self.datarevsearchmethod)
		MetadataRepository.errormsg( "metadatapath:" + self.metadatapath)
		MetadataRepository.errormsg( "streamname:" + self.streamname)


		

class MetadataRepository(pygit2.Repository):
	data_name = uuid.uuid5(uuid.NAMESPACE_X500, 'data').__str__()
	metadata_name = uuid.uuid5(uuid.NAMESPACE_X500, 'metadata').__str__()
	metadataref_default = "refs/heads/metadata"

	# We need two things to find the metadata:
	# 1 - A path to the file
	# 2 - A reference to a git commit for the metadata
	def __init__(self, repo_path, metadataref=metadataref_default, debug=False):

		# Initialise repository base class
		pygit2.Repository.__init__(self, repo_path)
		
		# Check if the repository is supported
		if self.is_bare:
			raise RepositoryNotSupported("Bare repositories not yet supported")
	
		# Save metadataref
		self.metadataref = metadataref

		# Save miscellaneous arguments
		self.debug = debug

		# Print debug info
		self.debugmsg("Repo=" + self.path)
		self.debugmsg("Metadata ref=" + self.metadataref)

	@staticmethod
	def errormsg(msg):
		sys.stderr.write("%s\n" % msg)

	def debugmsg(self, msg):
		if self.debug:
			MetadataRepository.errormsg(msg)

	@staticmethod
	def discover_repository(req_path, metadataref):
		parsedpath = MetadataPath(req_path, path_requires_search=False)

		# repo_search_path = req_path
		repo_search_path = parsedpath.metadatapath
		found = False

		# If we have been asked to search for a repository use discover_repository()
		while not found:
			try:
				# Remove trailing slash with os.path.abspath?
				repo_path = pygit2.discover_repository(repo_search_path)
				found = True

			# Repository could not be found, so start looking for a repository higher up
			# (discover_repository() only does this if the folder exists,
			# but we might have been passed a path that doesn't exist that does exist in repo)
			except KeyError:

				# Break if we have a blank string or have reached the root directory
				if repo_search_path in ["", os.path.abspath(os.sep)]:
					break

				# Otherwise, carry on looking up the tree
				else:
					repo_search_path = os.path.dirname(repo_search_path)

		if found:
			# Don't need to check whether metadata branch exists because we'll create it			
			# Return repository
			return repo_path
		else:
			raise KeyError("Could not find a Git repository")


	def save_metadata_blob(self, newfile, pathreq, force=False):
		path = self.parse_path_parameter(pathreq, fixdatarev=True)

		# Branch might not exist yet, so try to find the metadata branch,
		# otherwise create a new one
		try:
			# Find metadata branch
			currentmetadatacommit = self.get_metadata_commit(self.metadataref)
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
		datacommitid = self.get_data_commit(path.datarev).id.__str__()

		# Save metadata tree
		parentspath = self.get_metadata_blob_path(path.metadatapath, path.streamname, datacommitid)
		parentslist = parentspath.split(os.sep)
		toptreeid = self.write_tree_hierarchy(parentslist, newblobid, force=force)

		# Create a commit
		commitid = self.create_commit(
			metadatareftoupdate,
			pygit2.Signature('Mark', 'cms4@soton.ac.uk'),
			pygit2.Signature('Mark', 'cms4@soton.ac.uk'),
			"Updated metadata for " + path.metadatapath,
			toptreeid,
			commitparentids)

		if metadatareftoupdate is None:
			head_ref = self.create_reference(self.metadataref, commitid)

		self.debugmsg("Commit %s created." % (commitid))
		print "Metadata for '%s (%s)' saved to stream '%s' in '%s'." % (path.metadatapath, datacommitid, path.streamname, self.metadataref)

		return commitid

	def copy_metadata(self, sourcepathreq, destpathreq, force=False):

		source = self.parse_path_parameter(sourcepathreq, fixdatarev=False)
		dest = self.parse_path_parameter(destpathreq, fixdatarev=False)
		
		# Check the data revision supplied.
		# If the user specified None, we need to find the latest metadata for this path and ensure the
		# data hash matches (otherwise it's not committed).
		# What happens if it is a new version of the file that has been committed but has no metadata yet?
		# ...we don't know whether to update earlier commit or update specified commit.
		# ---> So, a set command must always specify the behaviour otherwise unexpected things might happen.
		if source.datarev is None or dest.datarev is None or source.metadatapath is None or dest.metadatapath is None:
			raise ParameterError("Source datarev and dest datarev must be specified for copy")

		# Find the data commit
		if source.datarevsearchmethod == DataRevisionMetadataSearchMethod.SearchBackForEarlierMetadataAllowed:
			sourcedatacommitwithobject = self.find_data_commit_with_object(source.datarev, source.metadatapath)
		elif source.datarevsearchmethod == DataRevisionMetadataSearchMethod.UseRevisionSpecifiedOnly:
			sourcedatacommitwithobject = self.get_data_commit(source.datarev)
		else:
			raise ParameterError("Data revision update method required")
		
		if dest.datarevsearchmethod == DataRevisionMetadataSearchMethod.SearchBackForEarlierMetadataAllowed:
			destdatacommitwithobject = self.find_data_commit_with_object(dest.datarev, dest.metadatapath)
		elif dest.datarevsearchmethod == DataRevisionMetadataSearchMethod.UseRevisionSpecifiedOnly:
			destdatacommitwithobject = self.get_data_commit(dest.datarev)
		else:
			raise ParameterError("Data revision update method required")
		
		sourcedatacommitwithobjectid = sourcedatacommitwithobject.id.__str__()
		destdatacommitwithobjectid = destdatacommitwithobject.id.__str__()

		MetadataRepository.errormsg("'{}' has been found in data commit {}".format(source.metadatapath, sourcedatacommitwithobjectid))
		sourcemetadatablobpath = self.get_metadata_blob_path(source.metadatapath, source.streamname, sourcedatacommitwithobjectid)
		destmetadatablobpath = self.get_metadata_blob_path(dest.metadatapath, dest.streamname, destdatacommitwithobjectid)
		MetadataRepository.errormsg("Metadata will be copied from '{}' to '{}'".format(sourcemetadatablobpath, destmetadatablobpath))

		# Get the metadata, not handling any exceptions if the blob is not found
		#sourcemetadatablob = self.get_metadata_blob(sourcestreamname, sourcedatacommitwithobjectid, path=sourcepath)

		#newcommitid = self.save_metadata_blob(sourcemetadatablob, deststreamname, destdatacommitwithobjectid, path=destpath, force=force)

	def get_data_commit(self, datarev):
		try:
			commit = self.revparse_single(datarev)
			if not isinstance(commit, pygit2.Commit):
				raise NoDataError("Could not find matching data " + datarev)
			else:
				return commit
		except KeyError:
			raise NoDataError("Could not find matching data " + datarev)

	def get_metadata_commit(self, metadataref):
		try:
			metadatacommit = self.revparse_single(metadataref)
			if not isinstance(metadatacommit, pygit2.Commit):
				raise MetadataCommitNotFoundError("Expected Commit for reference %s" % metadataref)
			else:
				return metadatacommit
		except KeyError:
			raise NoMetadataBranchError("No metadata could be found")

	def parse_path_parameter(self, pathreq, fixdatarev=False, path_requires_search=True):
		path = MetadataPath(pathreq, path_requires_search=path_requires_search, repo=self)

		# Please note that if we set the datarev to the new default of HEAD, to know whether
		# data has changed between the metadata's commit, we need to know the
		# requested data and the metadata's actual data commit. For example, if the user specified None:file1
		# then we will look up metadata in HEAD:file1.txt, we will need to check whether file1.txt
		# has changed in the working directory because the user did not explicitly specify HEAD:file1.txt.
		# However, if the user did specify HEAD:file1.txt we can then lookup the metadata for that
		# version of the file.
		if fixdatarev and path.datarev is None:
			path.datarev = self.generate_datarev(path)
			MetadataRepository.errormsg("NOTE: Data revision not specified. Assuming '{}'.".format(path.datarev))
			# If we get here then the file or folder exists in the HEAD commit
			
		return path

	# The metadata node is the path to the beginning of the metadata and contains streams and blobs
	def get_metadata_node_path(self, path):
		metadatanodepath = os.path.join(path, MetadataRepository.metadata_name)
		self.debugmsg("metadata node path = " + metadatanodepath)
		return metadatanodepath

	# The metadata stream is the path to the tree containing metadata blobs for each commit
	def get_metadata_stream_path(self, path, streamname):
		metadatanodepath = self.get_metadata_node_path(path)
		metadatastreampath = os.path.join(metadatanodepath, streamname)
		self.debugmsg("metadata stream path = " + metadatastreampath)
		return metadatastreampath
	
	# The metadata blob contains the metadata for a particular path, stream and data commit
	def get_metadata_blob_path(self, path, streamname, datacommitid):
		# metadatadatacommitid = self.find_latest_commitid_in_metadata(branchname, self.datarootcommit)
		metadatanodepath = self.get_metadata_stream_path(path, streamname)
		metadatablobpath = os.path.join(metadatanodepath, datacommitid)
		self.debugmsg("metadata blob path = " + metadatablobpath)
		return metadatablobpath

	def generate_datarev(self, path):
		if not isinstance(path, MetadataPath):
			raise ParameterError("Passed path was not an instance of MetadataPath")
		
		if path.repo is None:
			raise ParameterError("Passed a path without a repo")

		datarev = MetadataPath.datarev_default_get
		abspath = os.path.join(path.repo.workdir, path.metadatapath)
		if os.path.isfile(abspath):
			# Check what the status of the file is
			status = self.status_file(path.metadatapath)

			if status > pygit2.GIT_STATUS_CURRENT:
				raise MetadataInvalidError("File has been modified but not committed so this metadata is not valid. Use '{}:{}' syntax to see metadata.".format(datarev, path))
		elif os.path.isdir(abspath):
			# Try to find the directory in the revision specified
			try:
				expectedtree = self.revparse_single('%s:%s' % (datarev, path.metadatapath))
				if not isinstance(expectedtree, pygit2.Tree):
					raise ParameterError("Path does not exist and data revision not specified")
			except KeyError:
				raise ParameterError("Path does not exist and data revision not specified")
		else:
			# If it wasn't a file or a directory, report an error
			raise ParameterError("Path does not exist and data revision not specified")

		# If we get here then the file or folder exists in the HEAD commit
		return datarev

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

	# COPY FUNCTIONS
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

	# Given a data object and a commit, we compare the parent to the current commit to see
	# if this was the commit where the blob was added. If not added at this commit, we
	# call ourselves with the parent commit to check if the blob was added in the parent,
	# and so on until there are no more parents.
	def find_first_data_commit_with_blob(self, dataobject, currentcommit):
		currenttree = currentcommit.tree

		self.debugmsg("looking for %s in %s" % (dataobject.id, currentcommit.id))

		if len(currentcommit.parents) > 1:
			raise MetadataReadError("Merges not supported")
		elif len(currentcommit.parents) == 1:
			# Compare against the commit's parent
			parentcommit = currentcommit.parents[0]
			diff = currenttree.diff_to_tree(parentcommit.tree, swap=True)
		else:
			# No parent commit to compare against so we will see what has been added in the first commit
			parentcommit = None
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


	# LIST FUNCTIONS
	def list_metadata_in_stream(self, pathreq):
		# Get the path or generate it if not specified
		path = self.parse_path_parameter(pathreq, fixdatarev=False, path_requires_search=False)

		normpath = os.path.normpath(path.metadatapath)

		print "\n* Listing metadata for file path: '{}'\n* Data branch specified: '{}'\n* Stream specified: {}".format(normpath, path.datarev, path.streamname)

		# Find the parents of the specified datarev
		if path.datarev is not None:
			dataitemcommit = self.revparse_single("%s" % path.datarev)
			dataitemcommitparents = [commit.id.__str__() for commit in self.walk(dataitemcommit.id, pygit2.GIT_SORT_REVERSE)]
			self.debugmsg("parent commits %s " % dataitemcommitparents)

		outputformatstr = "{:40} {:40} {:15} {:11} {!s:19}"

		# Retrieve the data item requested if we can find it
		dataitemrequested = self.find_path_in_repository(path.datarev, path.metadatapath)

		# Retrieve metadata node for the given path
		metadatanode = self.get_metadata_stream(path.metadatapath, path.streamname)

		matchingstrings = []
		notmatchingstrings = []

		# Iterate around each metadata item defined for the given path
		listofmetadataentryids = [metadataentry.name for metadataentry in metadatanode]
		for datacommitwithmetadataid in listofmetadataentryids:

			# If we couldn't find the data item in the repository then we can't look up its metadata
			if dataitemrequested is None:
				datacommitwithmetadatastr = "Matching data could not be found"
				dataitemmatchesrequest = False
				matchingdataidstr = "Matching data could not be found"
			else:
				try:
					# Attempt to find data commit that metadata pertains to
					datacommitwithmetadata = self.get_data_commit(datacommitwithmetadataid)
					datacommitwithmetadatastr = datetime.datetime.fromtimestamp(datacommitwithmetadata.commit_time)

					# Attempt to find data item matching path
					matchingdataitem = self.revparse_single("%s:%s" % (datacommitwithmetadataid, path.metadatapath))

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

			# The item can match, but not be from a parent commit. These bools handle both scenarios
			metadatainheritable = (dataitemrequested is not None) and (path.datarev is not None) and (datacommitwithmetadataid in dataitemcommitparents) and (dataitemmatchesrequest)
			metadatainheritablestr = ("YES" if metadatainheritable else "NO")
			matchingdatastr = ("YES" if dataitemmatchesrequest else "NO")

			# if datarev is None or (dataitemmatchesrequest and metadatainheritable):
			outputstring = outputformatstr.format(datacommitwithmetadataid, matchingdataidstr, matchingdatastr, metadatainheritablestr, datacommitwithmetadatastr)
			if ((dataitemrequested is not None) or (path.datarev is None)) and dataitemmatchesrequest:
				matchingstrings.append(outputstring)
			else:
				notmatchingstrings.append(outputstring)

		# Format the table
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

	def log(self, pathreq):
		path=self.parse_path_parameter(pathreq, fixdatarev=True, path_requires_search=False)

		if path.datarev is None:
			raise ParameterError("Starting data revision must be specified")

		# Find the parents of the specified datarev
		dataitemcommit = self.revparse_single("%s" % path.datarev)
		dataitemcommitparents = [commit for commit in self.walk(dataitemcommit.id, pygit2.GIT_SORT_TIME)]

		metadatacommits ={}
		try:
			streamnamesforpath = [stream.name for stream in self.get_metadata_node(path.metadatapath)]
			for streamname in streamnamesforpath:
				commitsforstream = [commit.name for commit in self.get_metadata_stream(path.metadatapath, streamname)]
				for commitid in commitsforstream:
					if not commitid in metadatacommits:
						metadatacommits[commitid] = []
					metadatacommits[commitid].append(streamname)
			
		except MetadataBlobNotFoundError as e:
			pass

		metadatafound = False
		for commit in dataitemcommitparents:

			commit_info_string = "%s, %s" % (commit.id, datetime.datetime.fromtimestamp(commit.commit_time))
			
			if commit.id.__str__() in metadatacommits:
				print "M " + commit_info_string
				print " \\"
				metadatafound = True
				for streamname in metadatacommits[commit.id.__str__()]:
					print "  * Stream: %s" % streamname
			else:
				print "  " + commit_info_string
		
		if not metadatafound:
			print
			print "No metadata was found"
			print

	def find_path_in_repository(self, datarev, path):
		normpath = os.path.normpath(path)

		# Retrieve the item that the user wants us to list metadata for
		if datarev is None:
			# User did not specify a revision so we have to look on the file system
			try:
				# Without a data revision, we can only lookup a blob in the repository
				fullpath = os.path.join(self.workdir, path)
				dataitem = self.find_fs_blob_in_repository(fullpath)
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

	def get_metadata_tree(self, metadatatreepath, metadataref=None):
		# Find metadata branch
		if metadataref is None:
			metadataref = self.metadataref

		metaadatacommit = self.get_metadata_commit(metadataref)

		# Retrieve metadata node
		try:
			metadatatree = self.revparse_single("%s:%s" % (metaadatacommit.id, metadatatreepath))
			if not isinstance(metadatatree, pygit2.Tree):
				raise MetadataBlobNotFoundError("Could not find metadata tree")
			else:
				return metadatatree
		except KeyError:
			raise MetadataBlobNotFoundError("Could not find metadata tree")
	
	def get_metadata_node(self, path, metadataref=None):

		# Find path of metadata node
		metadatanodepath = self.get_metadata_node_path(path)
		metadatanode = self.get_metadata_tree(metadatanodepath, metadataref=metadataref)
		return metadatanode

	def get_metadata_stream(self, path, streamname, metadataref=None):

		# Find path of metadata node
		metadatastreampath = self.get_metadata_stream_path(path, streamname)
		metadatastream = self.get_metadata_tree(metadatastreampath, metadataref=metadataref)
		return metadatastream

	def get_metadata_blob(self, pathreq):

		# Parse path parameter
		path = self.parse_path_parameter(pathreq, fixdatarev=True)

		# Find metadata branch
		metaadatacommit = self.get_metadata_commit(self.metadataref)

		# Find the data commit
		datacommitid = self.get_data_commit(path.datarev).id.__str__()

		# Generate the path from the object requested, stream name and revision
		metadatablobpath = self.get_metadata_blob_path(path.metadatapath, path.streamname, datacommitid)

		# Try to get the blob
		try:
			metadatablob = self.revparse_single("%s:%s" % (metaadatacommit.id, metadatablobpath))
			if not isinstance(metadatablob, pygit2.Blob):
				raise MetadataBlobNotFoundError("Could not find metadata blob in the tree")
			else:
				return metadatablob
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

class MetadataRepository_old(pygit2.Repository):

# 	def check_path_request(self, path):
# 		"""Work out the path for the metadata request"""
# 
# 		# If no path was specified, use the default for the repository object
# 		if path is None:
# 			path = self.rel_req_path
# 
# 		# Remove start slash from the request as we start searching from the root anyway
# 		if os.path.isabs(path):
# 			path = path[1:]
# 
# 		return path


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
			datacommitwithobject = self.get_data_commit(datarev)
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
