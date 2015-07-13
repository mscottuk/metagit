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

class MetadataRepo:
	MetadataBlobNotFoundError = MetadataBlobNotFoundError
	
	def __init__(self):
	
		# Parse the user arguments
		self.args = args
	
		if self.args.path is None:
			self.req_path=os.getcwd()
		else:
			self.req_path=self.args.path

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
			raise NoRepositoryError("Could not find a Git repository")

		self.repo = pygit2.Repository(self.repodir)
		self.basedir = os.path.dirname(self.repodir)
		self.rel_req_path=self.abs_req_path[len(self.basedir)+1:]
		
		if self.args.verbose:
			print "Repo=" + self.repodir
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
			raise MetadataBlobNotFoundError("No metadata not found for " + e.__str__())
	
	def get_metadata(self):
		self.branch = self.repo.lookup_branch(self.args.branch)

		if self.branch is None:
			raise NoMetadataBranchError("Could not find metadata branch in the repository")
		else:
			self.commit = self.branch.get_object() # Save commit for later
			tree = self.commit.tree
			blob = self.get_blob(self.rel_req_path.split(os.sep),tree)
			return blob
		
	def is_action(self,action):
		return self.args.action & action == action
		
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
