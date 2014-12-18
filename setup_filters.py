from optparse import OptionParser
from common import shared
import re
import json
import sys

def saveFilters(name, filters):
    with open(name,'w') as outfile:
        json.dump(filters, outfile,indent=4, sort_keys=True)


def listVersions(project, pattern):
    versions = shared.jiraquery(options,"/rest/api/latest/project/" + project + "/versions")
    #versionmatch = re.compile('4.2.(?!x).*')
    versionmatch = re.compile(pattern)
    foundversions = []
    for version in versions:
       # print version['name']
        if versionmatch.match(version['name']):
            foundversions.append('"' + version['name'] + '"')

    result = ", ".join(foundversions)

    
    return result

usage = "usage: %prog -u <user> -p <password> -f <filters.json>\nCreate/maintain set of filters defined in filters.json."

parser = OptionParser(usage)

#todo: move the shared options to common ?
parser.add_option("-u", "--user", dest="username", help="jira username")
parser.add_option("-p", "--pwd", dest="password", help="jira password")
parser.add_option("-s", "--server", dest="jiraserver", default="https://issues.jboss.org", help="Jira instance")
parser.add_option("-f", "--filters", dest="filterfile", default="filters.json", help="Filters.json")
parser.add_option("-v", "--verbose", dest="verbose", action="store_true", help="more verbose logging")
(options, args) = parser.parse_args()

if not options.username or not options.password:
    parser.error("Missing username or password")

if options.filterfile:
    #print "Force enabling global shared filters. Will not have any effect if user is not allowed to globally share objects in jira."
    #shared.jiraupdate(options, "/rest/api/latest/filter/defaultShareScope", { 'scope': 'GLOBAL' })

    print "Load constants"
    constantdef = json.load(open("constants.json", 'r'))
    constants = {}
    for name, fields in constantdef.items():
        method = getattr(sys.modules[__name__], fields['function'])
        del fields['function']
        constants[name] = method(**fields)
        print name + "->" + constants[name]
    
    print "Using filters defined in " + options.filterfile
    filters = json.load(open(options.filterfile, 'r'))

    newfilters = filters.copy()
    for name, fields in filters.items():
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
        saveFilters(options.filterfile, newfilters) # saving every succesful iteration to not loose a filter id 

#    saveFilters(options.filterfile, newfilters)
    



