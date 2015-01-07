from optparse import OptionParser
from common import shared
import urllib2
import re
import json
import sys
import os
import time
import datetime

def saveFilters(name, filters):
    with open(name,'w') as outfile:
        json.dump(filters, outfile,indent=4, sort_keys=True)

def loadConstants():
    constants = {}
    if os.path.isfile("constants.json"):
        print "Loading constants from constants.json"
        constantdef = json.load(open("constants.json", 'r'))
        for name, fields in constantdef.items():
            method = getattr(sys.modules[__name__], fields['function'])
            del fields['function']
            constants[name] = method(**fields)
            print name + "->" + constants[name]
    
    return constants

def isCodefrozenToday(v):
    result = re.search(".*codefreeze:.*([0-9]{4}.[0-9]{2}.[0-9]{2}).*", v['description'])
    if result:
        ts = time.mktime(datetime.datetime.strptime(result.group(1), "%Y/%m/%d").timetuple())
        if ts <= time.time():
            return True

    return False

def listVersions(project, pattern=".*", released=None, hasReleaseDate=None, archived=None, hasStartDate=None, codefrozen=None, lowerLimit=None, upperLimit=None, index=None):
    """Return list of versions for a specific project matching a pattern and a list of optional filters.

           arguments:
            project -- the jira project key (i.e. 'JBIDE') (required)
            pattern -- regular expression that the version name should match (i.e. '4.2.*') (default=.*)
            released -- boolean to state if the version should be released or not. (default=None)
            archived -- boolean to state if the version should be archived or not. (default=None)
            hasStartDate -- boolean to state if the version should have a start date. (default=None)
            hasReleaseDate -- boolean to state if the version should have a released date. (default=None)
            codefrozen -- boolean if description of version contains (codefreeze: <date>) and date has occurred true will include it otherwise exclude it. 
            upperLimit -- upper limit (default=None)
            lowerLimit -- lower limit (default=None)
            index -- integer to state which index to get (supports negative indexing too, -1=last element), if index out of range nothing is returned. (default=None)

            examples:
            listVersions("JBIDE", "4.2.*") -- versions in JBIDE starting with "4.2."
            listVersions("JBIDE", "4.2.*", upperLimit=2) -- first two version of 4.2.*
            listVersions("JBIDE", "4.2.*", released=False, upperLimit=2) -- first two version that are released in 4.2.*
            listVersions("JBIDE", "4.2.*", released=False) -- non-released 4.2.* versions
            listVersions("JBIDE", "4.2.*|4.3.*", released=False, hasReleaseDate=True) -- non-released that has release date in either 4.2 or 4.3 streams
            listVersions("JBIDE", "4.2.*|4.3.*", released=False, hasStartDate=True) -- non-released that has start date in either 4.2 or 4.3 streams
            listVersions("JBIDE", ".*", archived=True, hasReleaseDate=True, lowerLimit=2, lowerLimit=4)
    """

    versions = shared.jiraquery(options,"/rest/api/latest/project/" + project + "/versions")
    print pattern
    versionmatch = re.compile(pattern)
    foundversions = []
    for version in versions:
        if versionmatch.match(version['name']):
            foundversions.append(version)

    if released is not None:
        foundversions = filter(lambda v: released == v['released'], foundversions)
        
    if hasReleaseDate is not None:
        foundversions = filter(lambda v: 'releaseDate' in v, foundversions)

    if hasStartDate is not None:
        foundversions = filter(lambda v: 'startDate' in v, foundversions)

    if archived is not None:
        foundversions = filter(lambda v: archived == v['archived'], foundversions)

    if codefrozen is not None:
        foundversions = filter(lambda v: isCodefrozenToday(v), foundversions)
                
    if upperLimit or lowerLimit:
        foundversions = foundversions[lowerLimit:upperLimit]

    if index is not None:
        try:
            foundversions = [foundversions[index]]
        except IndexError:
            foundversions = []

    foundversions = map(lambda v: v['name'], foundversions)
    
    return ", ".join(foundversions)

    

usage = "usage: %prog -u <user> -p <password> -f <filters.json>\nCreate/maintain set of filters defined in filters.json."

parser = OptionParser(usage)

#todo: move the shared options to common ?
parser.add_option("-u", "--user", dest="username", help="jira username")
parser.add_option("-p", "--pwd", dest="password", help="jira password")
parser.add_option("-s", "--server", dest="jiraserver", default="https://issues.jboss.org", help="Jira instance")
parser.add_option("-f", "--filters", dest="filterfiles", default="filters.json", help="comma separated list of filters to setup")
parser.add_option("-v", "--verbose", dest="verbose", action="store_true", help="more verbose logging")
(options, args) = parser.parse_args()

if not options.username or not options.password:
    parser.error("Missing username or password")


if options.filterfiles:
    #print "Force enabling global shared filters. Will not have any effect if user is not allowed to globally share objects in jira."
    #shared.jiraupdate(options, "/rest/api/latest/filter/defaultShareScope", { 'scope': 'GLOBAL' })

    constants = loadConstants()

    
    filterfiles = options.filterfiles.split(',')
    for filterfile in filterfiles:
        print "Processing filters found in " + filterfile
        filters = json.load(open(filterfile, 'r'))

        newfilters = filters.copy()
        for name, fields in filters.items():
            try:
                data = {
                    'name': name,
                    'description': fields['description'],
                    'jql': fields['jql'] % constants,
                    'favourite' : 'true'
                }
        
                if 'id' in fields:
                    print 'updating ' + name
                    fields['id'] = shared.jiraupdate(options, "/rest/api/latest/filter/" + fields['id'], data)['id']
                else:
                    print 'creating ' + name
                    fields['id'] = shared.jirapost(options, "/rest/api/latest/filter", data)['id']

                newfilters[name] = fields
                saveFilters(filterfile, newfilters) # saving every succesful iteration to not loose a filter id 
            except urllib2.HTTPError, e:
                print "Problem with setting up filter %s with JQL = %s" % (data['name'], data['jql']);
                
    



