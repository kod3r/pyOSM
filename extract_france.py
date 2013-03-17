#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
	extract_france.py
	commande line tool
	Parse XML file (obtain from OpenStreetMap OSM) to extract Administrative boundary
	Require the XML file from OSM describing the relation (here 11980.xml)
	
	Parse a OSM'XML local data file, extract france boundary (relation id=11980)
	concanate ways, reorder nodes and ways into a single path.
	
	Pierre-Alain Dorange, november 2010
"""

# standard python modules
from xml.etree import ElementTree	# fast xml parser module
import string
import time, datetime
import os.path
import sys,getopt	# handle commande-line arguments
import sqlite3

# external module
import pyOSM

__version__=0.1
france_id=11980
france_file="11980.xml"
#france_id=-123
#france_file="test_france.xml"
  
def ensure_dir(f):
	""" check and create directory if it doesn't exist on local disk """
	d=os.path.dirname(f)
	if not os.path.exists(d):
		os.makedirs(d)

class OSMCountry(pyOSM.Way):
	def __init__(self,id=-1):
		pyOSM.Way.__init__(self,id)
		self.population=0
		self.region=None
		self.node=pyOSM.Node()
		self.area=pyOSM.Area()
		self.level=2
		
	def show(self,short=True):
			print u"Pays %s" % self.name,
			print "(osm#%d) : " % self.osm_id,
			print "pop=%d" % self.population
			if self.node:
				print "\t@ (%.3f,%.3f, id=%d, name=%s)" % (self.node.location[0],self.node.location[1],self.node.osm_id,self.node.name)
			if self.area:
				print "\tboundary has %d node(s)" % self.area.nb_nodes()

class OSMFrance():
	"""	
		Handle France administrative areas 
		La frontière Française est décrite par la relation 11980 qui contient elle même des relations contenant des Way.
		Voir "France Boundary Pyramidal Construction" :
			<http://wiki.openstreetmap.org/wiki/France_boundary_pyramidal_construction>
			
		1. Trouver la relation mère
		2. Repérer les relations filles
		3. extraire les chemines (ways)
		4. extraire les points (nodes) corrspondants
		5. ordonner les ways
	"""
	def __init__(self):
		self.pays=[]
		
	def parse_osm(self,fname,dname="area",get_area=False,override_area=False):
		tree=ElementTree.parse(fname)
		root=tree.getroot()
		relations=root.getiterator("relation")
		ways=root.getiterator("way")
		nodes=root.getiterator("node")
		print "scanning",len(relations),"relations"
		nbAdmin=0
		o=None
		relationsID=[]
		for r in relations:	# scan each relation
			name=""
			pop=0
			admin_level=0
			try:
				id=long(r.get("id"))
				if id==france_id:
					for tag in r.getiterator("tag"):	# for one relation, scan each tags
						k=tag.get("k")
						if k=='admin_level':
							nbAdmin=nbAdmin+1
							try:
								v=int(tag.get("v"))
								admin_level=v
							except:
								print "* error relation #%d : retrieving 'place'" %id
						if k=='name':
							name=tag.get("v")
						if k=='population':
							try:
								pop=int(tag.get("v"))
							except:
								pop=-1
								
					print "France found:",id,name
					o=OSMCountry(id)
					self.pays.append(o)
					o.name=name
					o.population=pop
					o.level=admin_level
					is_node=-1
					for m in r.getiterator("member"):
						ref=long(m.get("ref"))
						type=m.get("type")
						role=m.get("role")
						if type=="node" and (role=="capital" or role=="admin_centre" or role=="admin_center"):	# has an admin_centre
							is_node=ref
						if type=="relation":
							relationsID.append(ref)
					if is_node>0:	# store the admin_centre
						o.node.osm_id=is_node
						try:
							o.node.name="not found"
							for n in nodes:
								ref=long(n.get("id"))
								if ref==is_node:
									ll=float(n.get("lat"))
									lo=float(n.get("lon"))
									o.node.location=(ll,lo)
									try:
										for tag in n.getiterator("tag"):
											k=tag.get("k")
											if k=="name":
												o.node.name=tag.get("v")
									except:
										o.node.name="admin_centre has no name"
									break
						except:
							o.node.location=(0.0,0.0)
							print "admin_centre %d for %s has no location" % (is_node,o.name)
			except:
				id=-1
				print "* error retrieving attribute 'id' for admin relation"
				print sys.exc_info()
		
		if o!=None:	# if we found the mother relation, then proceed on sister relation
			waysID=[]
			nodesID=[]
			nodearea=[]
			wayarea=[]
			is_node=-1
			print "scanning %d relations" % len(relations)
			for r in relations:	# scan each relation for sister relations
				name=""
				try:
					id=long(r.get("id"))
				except:
					id=-1
					print "* error retrieving attribute 'id' for admin relation"
			
				if id in relationsID:	#it's a sister relation, handle
					for tag in r.getiterator("tag"):	# for one relation, scan each tags
						k=tag.get("k")					
						if k=='admin_level':
							nbAdmin=nbAdmin+1
						if k=='name':
							name=tag.get("v")
					for m in r.getiterator("member"):
						ref=long(m.get("ref"))
						type=m.get("type")
						role=m.get("role")
						if type=="way":
							waysID.append(ref)
							wayarea.append(pyOSM.Way(ref))
			print "Scanning %d way(s)" % len(waysID)
			if len(waysID)>0:
				for w in ways:
					wr=long(w.get("id"))
					wo=pyOSM.is_in(wayarea,wr)
					if wr in waysID:
						for n in w.getiterator("nd"):
							nr=long(n.get("ref"))
							nodesID.append(nr)
							if wo:
								nodearea.append((wr,nr))
								wo.add_node(pyOSM.Node(nr))
			print "Retrieving %d node(s)" % len(nodesID)
			if len(nodesID):
				nb_nodes=0
				lat,lon=(0.0,0.0)
				for n in nodes:
					ref=long(n.get("id"))
					if ref in nodesID:
						nb_nodes=nb_nodes+1
						ll=float(n.get("lat"))
						lo=float(n.get("lon"))
						if ll and lo:
							lat=lat+ll
							lon=lon+lo
						for wr,nr in nodearea:
							if nr==ref:
								wo=pyOSM.is_in(wayarea,wr)
								if wo:
									no=wo.get_node(ref)
									if ll==0.0 or lo==0.0:
										print "bad location for node %d in way %d" % (wr,nr)
									no.location=(ll,lo)
								else:
									print "wo %d not found for node %d" % (wr,nr)
				if nb_nodes>0:
					lat=lat/nb_nodes
					lon=lon/nb_nodes
				# sort ways
				o.area.add_sorted_ways(wayarea)
				noloc=[]
				for n in o.area.nodes:
					ll,lo=n.location
					if ll==0.0 or lo==0.0:
						noloc.append(n.osm_id)
				if len(noloc)>0:
					print "\t%d node without location" % len(noloc)
					print "\t",noloc
				o.area.osm_id=o.osm_id
				o.area.name=o.name
				filename=os.path.join(dname,"fr%d_%s.xml" % (o.level,o.name))
				ensure_dir(filename)
				o.area.save(filename)
				o.node.osm_id=is_node
				if is_node<0:
					o.node.name="barycenter"
					o.node.location=(lat,lon)						
			o.show(False)					
		return nbAdmin

def main(argv):
	
	file=france_file

	print "-------------------------------------------------"
	print "Recherche des frontères de la France dans un fichier OSM/XML..."

	admin=OSMFrance()

	print "Parsing for admin_level"
	t0=time.time()
	nbAdmin=admin.parse_osm(file)
	t0=time.time()-t0
	print "> parsing admin : %.1f seconds" % t0
	
	print "%d country (admin_level=2)" % len(admin.pays)
	print "-------------------------------------------------"

if __name__ == '__main__' :
    main(sys.argv[1:])
	