import bugzilla
from jira.client import JIRA
from optparse import OptionParser
import urllib
import pprint
from common import shared
import pickle

httpdebug = False

### Enables http debugging
if httpdebug:
    import requests
    import logging
    import httplib
    httplib.HTTPConnection.debuglevel = 1
    logging.basicConfig() # you need to initialize logging, otherwise you will not see anything from requests
    logging.getLogger().setLevel(logging.DEBUG)
    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(logging.DEBUG)
    requests_log.propagate = True

pp = pprint.PrettyPrinter() 

def lookup_proxy(options, bug):

    #TODO: should keep a local cache from BZ->JIRA to avoid constant querying
    payload = {'jql': 'project = ERT and summary ~ \'EBZ#' + str(bug.id) +'\'', 'maxResults' : 5}
    print payload
    data = shared.jiraquery(options, "/rest/api/2/search?" + urllib.urlencode(payload))
    count = len(data['issues'])
    if(count == 0):
        return 
    elif(count == 1):
        return data['issues'][0]
    else:
        print "WARNING: Multiple issues found for " + str(bug.id)
        print data['issues']
        return 


## Create the jira dict object for how the bugzilla *should* look like
def create_proxy_jira_dict(options, bug):

    
    issue_dict = {
        'project' : { 'key': 'ERT' },
        'summary' : bug.summary + ' [EBZ#' + str(bug.id) + "]",
        'description' : bug.getcomments()[0]['text'], # todo - this loads all comments...everytime. probably should wait to do this once it is absolutely needed.
        'issuetype' : { 'name' : 'Task' }, # No notion of types in bugzilla just taking the most generic/non-specifc in jira
        'priority' : { 'name' : bz_to_jira_priority(options, bug) },
        'labels' :   [ 'bzira', bug.component ],
        #'fixVersions' : [{ "name" : jbide_fixversion }],
        'components' : [{ "name" : bug.product }]
    }
    return issue_dict

bz2jira_priority = {
     'blocker' : 'Blocker',
     'critical' : 'Critical',
     'major' : 'Major',
     'normal' : 'Major',
     'minor' : 'Minor',
     'trivial' : 'Trivial',
     'enhancement' : 'Trivial' #TODO: is bz enhancement really indictor for type is feature or is it purely a priority/complexity flag ?
    }
    
def bz_to_jira_priority(options, bug):
    return bz2jira_priority[bug.severity] # jira is dumb. jira priority is severity.

usage = "usage: %prog -u <user> -p <password> \nCreates proxy issues for bugzilla issues in jira"

parser = OptionParser(usage)
parser.add_option("-u", "--user", dest="username", help="jira username")
parser.add_option("-p", "--pwd", dest="password", help="jira password")
parser.add_option("-s", "--server", dest="jiraserver", default="https://issues.stage.jboss.org", help="Jira instance")
parser.add_option("-d", "--dry-run", dest="dryrun", action="store_true", help="do everything but actually creating issues")
parser.add_option("-v", "--verbose", dest="verbose", action="store_true", help="be verbose")

(options, args) = parser.parse_args()

if not options.username or not options.password:
    parser.error("Missing username or password")

print "Logging in to jira...."
jira = JIRA(options={'server':options.jiraserver}, basic_auth=(options.username, options.password))


bz = bugzilla.Bugzilla(url="https://bugs.eclipse.org/bugs/xmlrpc.cgi")

query = bz.url_to_query("https://bugs.eclipse.org/bugs/buglist.cgi?status_whiteboard=RHT")
 
issues = bz.query(query)


bugs = []

components = jira.project_components('ERT')

for bug in issues:
    print '%s - %s [%s, %s, [%s]] -> %s' % (bug.id, bug.summary, bug.product, bug.component, bug.target_milestone, bug.weburl)

    issue_dict = create_proxy_jira_dict(options, bug)

   ## ensure the product name exists as a component
    if(not next((c for c in components if bug.product == c.name), None)): 
        comp = jira.create_component(bug.product, "ERT")
        components = jira.project_components('ERT')
    
    proxyissue = lookup_proxy(options, bug)
    
    if(proxyissue):
        print str(bug.id) + " already proxied at " + proxyissue['key']
        #print str(proxyissue)
        fields = {}
        if (not next((c for c in proxyissue['fields']['components'] if bug.product == c['name']), None)):
            #TODO: this check for existence in list of components
            # but then overwrites anything else. Problematic or not ?
            updcomponents = [{"name" : bug.product}]
            fields["components"] = updcomponents

        if len(fields)>0:
            print "Updating " + proxyissue['key'] + " with " + str(fields)
            isbug = jira.issue(proxyissue['key'])
            isbug.update(fields)
            
    else:
        if(options.dryrun):
            print "Wanted to create " + str(issue_dict)
        else:
            newissue = jira.create_issue(fields=issue_dict)
            link = {"object": {'url': bug.weburl, 'title': "Original Eclipse Bug"}}
            jira.add_simple_link(newissue,
                                 object=link)
            print "Created " + newissue.key
            bugs.append(newissue)

raw_input("Press Enter to delete...or ctrl+c to be ok with the created content")

for b in bugs:
    print "Deleting " + str(b)
    b.delete()
    
        
