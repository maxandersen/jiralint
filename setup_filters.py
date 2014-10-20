from optparse import OptionParser
from common import shared 
import json

usage = "usage: %prog -u <user> -p <password> -f <filters.json>\nCreate/maintain set of filters defined in filters.json."

parser = OptionParser(usage)

#todo: move the shared options to common ?
parser.add_option("-u", "--user", dest="username", help="jira username")
parser.add_option("-p", "--pwd", dest="password", help="jira password")
parser.add_option("-s", "--server", dest="jiraserver", default="https://issues.jboss.org", help="Jira instance")
parser.add_option("-f", "--filters", dest="filterfile", default="filters.json", help="Filters.json")
parser.add_option("-d", "--dry-run", dest="dryrun", action="store_true", help="do everything but actually sending mail")
parser.add_option("-v", "--verbose", dest="verbose", action="store_true", help="dump email bodies to console")

(options, args) = parser.parse_args()

if not options.username or not options.password:
    parser.error("Missing username or password")

if options.filterfile:
    print "Using filters defined in " + options.filterfile
    filters = json.load(open(options.filterfile, 'r'))

    newfilters = {}
    for name, fields in filters.items():
        data = {
                'name': name,
                #'description': fields['description'],
                'jql': fields['jql']
        }
        if 'id' in fields:
            print 'updating ' + name
            data['name'] = data['name'] + '_new'
            fields['id'] = shared.jiraupdate(options, "/rest/api/latest/filter/" + fields['id'], data)['id']
        else:
            print 'creating ' + name
            fields['id'] = shared.jirapost(options, "/rest/api/latest/filter", data)['id']

        newfilters[name] = fields
            
    with open('filters.json','w') as outfile:
        json.dump(newfilters, outfile,indent=4, sort_keys=True)
        
