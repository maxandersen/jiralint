import bugzilla
from jira.client import JIRA
from optparse import OptionParser
import urllib
import pprint
from common import shared
import pickle
import re
from datetime import datetime
from datetime import timedelta
import time
import pytz
import sys

httpdebug = False

NO_VERSION = "!  _NO_VERSION_!"

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
    data = shared.jiraquery(options, "/rest/api/2/search?" + urllib.urlencode(payload))
    count = len(data['issues'])
    if(count == 0):
        return 
    elif(count == 1):
        return data['issues'][0]
    else:
        print "[WARN] Multiple issues found for " + str(bug.id)
        print data['issues']
        return 


## Create the jira dict object for how the bugzilla *should* look like
def create_proxy_jira_dict(options, bug):

    jiraversion  = bz_to_jira_version(options, bug)

    fixversion=[]
    if (jiraversion and jiraversion != NO_VERSION): 
        fixversion=[{ "name" : jiraversion }]
    
    issue_dict = {
        'project' : { 'key': 'ERT' },
        'summary' : bug.summary + ' [EBZ#' + str(bug.id) + "]",
        'description' : bug.getcomments()[0]['text'], # todo - this loads all comments...everytime. probably should wait to do this once it is absolutely needed.
        'issuetype' : { 'name' : 'Task' }, # No notion of types in bugzilla just taking the most generic/non-specifc in jira
        'priority' : { 'name' : bz_to_jira_priority(options, bug) },
        'labels' :   [ 'bzira', bug.component ],
        'fixVersions' : fixversion,
        'components' : [{ "name" : bug.product }]
    }

    return issue_dict

def map_linuxtools(version):
    #TODO: make this use real neon versions.
    #TODO: curently based on map from xcoulon
    versions = {
        "4.2.1" : "Mars.2",
        "4.2" : "Mars.2",
        "4.1" : "Mars.1",
        "4.0" : "Mars",
        "---" : NO_VERSION
        }
    return versions.get(version, None)

bzprod_version_map = {
    "WTP Incubator" : (lambda version: NO_VERSION),

    # TODO ensure this works for 3.8.x -> Neon.x 
    "JSDT" : (lambda version: re.sub(r"3.8(.*)", r"Neon\1", version)),
    "WTP Source Editing" : (lambda version: re.sub(r"3.8(.*)", r"Neon\1", version)),

    # TODO ensure this works for 4.6.x -> Neon.x 
    "Platform" : (lambda version: re.sub(r"4.6(.*)", r"Neon\1", version)),

    # 4.2.1 -> Mars.2
    # 5.0.0 -> Neon.?
    "Linux Tools" : map_linuxtools,

    "m2e" : (lambda version: NO_VERSION)
    
    }


    
def bz_to_jira_version(options, bug):
    """Return corresponding jira version for bug version. None means mapping not known. NO_VERSION means it has no fixversion."""
    bzversion = bug.target_milestone
    b2j = None
    
    if bug.product in bzprod_version_map:
        b2j = bzprod_version_map[bug.product]
        jiraversion = b2j(bzversion)
        if (jiraversion):
            if (options.verbose):
                print "[DEBUG] " + "Mapper: " + bug.product + " / " + bzversion + " -> " + str(jiraversion)
            return jiraversion
        else:
            print "[ERROR] Unknown version for " + bug.product + " / " + bzversion
    else:
        print "[ERROR] No version mapper found for " + bug.product

    

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

def parse_options():
    usage = "Usage: %prog -u <user> -p <password> \nCreates proxy issues for bugzilla issues in jira"

    parser = OptionParser(usage)
    parser.add_option("-u", "--user", dest="username", help="jira username")
    parser.add_option("-p", "--pwd", dest="password", help="jira password")
    parser.add_option("-s", "--server", dest="jiraserver", default="https://issues.stage.jboss.org", help="Jira instance")
    parser.add_option("-d", "--dry-run", dest="dryrun", action="store_true", help="do everything but actually creating issues")
    parser.add_option("-v", "--verbose", dest="verbose", action="store_true", help="be verbose")
    # TODO should we support min age in hours instead of days? How often do we want to run this script?
    parser.add_option("-m", "--min-age", dest="minimum_age_to_process", help="if bugzilla has not changed in more than X days, do not process it")
    parser.add_option("-S", "--start-date", dest="start_date", default="", help="use this start date (yyyy-mm-dd) as the threshhold from which to query for bugzillas")

    (options, args) = parser.parse_args()

    if not options.username or not options.password:
        parser.error("Missing username or password")

    return options


options = parse_options()

# TODO cache results locally so we don't have to keep hitting live server to do iterations
bzserver = "https://bugs.eclipse.org/"
basequery = bzserver + "bugs/buglist.cgi?status_whiteboard=RHT"

# get current datetime in UTC for comparison to bug.delta_ts, which is also in UTC; use this diff to ignore processing old bugzillas
now = datetime.utcnow()
if (options.verbose):
    print "[DEBUG] " + "Current datetime: " + str(now) + " (UTC)"
    print "" 

# calculate relative date if options.start_date not provided but minimum_age_to_process is provided
if (options.start_date):
    last_change_time = datetime.strptime(str(options.start_date),'%Y-%m-%d')
elif (options.minimum_age_to_process):
    last_change_time = now - timedelta(days=int(options.minimum_age_to_process))
else:
    last_change_time = None
    
# to query only 1 week, 1 day, 3hrs of recent changes:
# https://bugs.eclipse.org/bugs/buglist.cgi?chfieldfrom=1w&status_whiteboard=RHT&order=changeddate%20DESC%2C
# https://bugs.eclipse.org/bugs/buglist.cgi?chfieldfrom=1d&status_whiteboard=RHT&order=changeddate%20DESC%2C
# https://bugs.eclipse.org/bugs/buglist.cgi?chfieldfrom=3h&status_whiteboard=RHT&order=changeddate%20DESC%2C
# but since chfieldfrom not supported in xmlrpc, use last_change_time instead with specific date, not relative one

if (last_change_time):
    query = basequery + "&last_change_time=" + last_change_time.strftime('%Y-%m-%d+%H:%M')
else:
    query = basequery
    
bz = bugzilla.Bugzilla(url=bzserver + "bugs/xmlrpc.cgi")

print "[DEBUG] " + "Querying bugzilla: " + query
    
issues = bz.query(bz.url_to_query(query))

print "[DEBUG] " + "Found " + str(len(issues)) + " bugzillas to process"

bugs = []

print "[INFO] " + "Logging in to " + options.jiraserver
jira = JIRA(options={'server':options.jiraserver}, basic_auth=(options.username, options.password))
components = jira.project_components('ERT')
if (options.verbose):
    print "[DEBUG] " + "Found " + str(len(components)) + " components in JIRA"
    print "" 

for bug in issues:
    # bug.delta_ts = bugzilla last changed date, eg., 20160106T09:50:33

    
    changeddate = datetime.strptime(str(bug.delta_ts), '%Y%m%dT%H:%M:%S')
    difference = now - changeddate

    if(options.verbose):
        print '[DEBUG] %s - %s [%s, %s, [%s]] {%s} -> %s (%s)' % (bug.id, bug.summary, bug.product, bug.component, bug.target_milestone, bug.delta_ts, bug.weburl, difference)
    else:
        sys.stdout.write('.')
        
    issue_dict = create_proxy_jira_dict(options, bug)

    
    ## ensure the product name exists as a component
    if(not next((c for c in components if bug.product == c.name), None)): 
        comp = jira.create_component(bug.product, "ERT")
        components = jira.project_components('ERT')
        
    proxyissue = lookup_proxy(options, bug)
        
    if(proxyissue):
        if(options.verbose):
            print "[INFO] " + bzserver + str(bug.id) + " already proxied as " + options.jiraserver + "/browse/" + proxyissue['key']
        #print str(proxyissue)
        fields = {}
        if (not next((c for c in proxyissue['fields']['components'] if bug.product == c['name']), None)):
            #TODO: this check for existence in list of components
            # but then overwrites anything else. Problematic or not ?
            updcomponents = [{"name" : bug.product}]
            fields["components"] = updcomponents

        # TODO this doesn't seem to actually change a fixversion field
        if len(fields)>0:
            print "Updating " + proxyissue['key'] + " with " + str(fields)
            isbug = jira.issue(proxyissue['key'])
            isbug.update(fields)
    
    else:
        if(options.dryrun is not None):
            print "[INFO] Want to create jira for " + str(bug)
            if(options.verbose):
                print "[DEBUG] " + str(issue_dict)
        else:
            newissue = jira.create_issue(fields=issue_dict)
            link = {"object": {'url': bug.weburl, 'title': "Original Eclipse Bug"}}
            print "[INFO] Created " + options.jiraserver + "/browse/" + newissue.key
            jira.add_simple_link(newissue, object=link)
            bugs.append(newissue)


# Prompt user to accept new JIRAs or delete them
if(options.dryrun is None): 
    accept = raw_input("Accept created JIRAs? [Y/n] ")
    if accept.capitalize() in ["N"]:
        for b in bugs:
            print "[INFO] " + "Delete " + options.jiraserver + "/browse/" + str(b)
            b.delete()

