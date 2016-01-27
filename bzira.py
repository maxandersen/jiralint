import bugzilla
from jira.client import JIRA, JIRAError
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
from collections import defaultdict

httpdebug = False

NO_VERSION = "!_NO_VERSION_!"

## Jira Project used for the Eclipse release train 
ECLIPSE_PROJECT = "ERT"

components = []
versions = []

## failure data
missing_versions = defaultdict(set)
jira_failure = defaultdict(set)

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

transitionmap = {
   ("Open", None, "Open", None) : None, # its already correct
   ("Open", None, "Resolved", "Done") : {"id" : "5", "resolution" : "Done" }, 
   ("Open", None, "Closed", "Cannot Reproduce Bug") : {"id" : "3", "resolution" : "Cannot Reproduce Bug" },
   ("Open", None, "Resolved", "Duplicate Issue") : {"id" : "2", "resolution" : "Duplicate Issue"},
   ("Open", None, "Reopened", None) : None, # can't go to reopen without closing so just leaving it in open
   ("Open", None, "Coding In Progress", None) : {"id" : "4"}

   }
    
def lookup_proxy(options, bug):

    #TODO: should keep a local cache from BZ->JIRA to avoid constant querying
    payload = {'jql': 'project = ' + ECLIPSE_PROJECT + ' and summary ~ \'EBZ#' + str(bug.id) +'\'', 'maxResults' : 5}
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

    ## check version exists, if not don't create proxy jira.
    if(not next((v for v in versions if jiraversion == v.name), None)):
        if(jiraversion and jiraversion != NO_VERSION): 
            print "[ERROR] Version '" + jiraversion + "' mapped from '" + bug.target_milestone + "' not found in " + ECLIPSE_PROJECT + ". Please create it or fix the mapping. Bug: " + str(bug)
            accept = raw_input("Create " + jiraversion + " ?")
            if accept.capitalize() in "Y":
                newv = jira.create_version(jiraversion, ECLIPSE_PROJECT)
                global versions
                versions = jira.project_versions(ECLIPSE_PROJECT)
                jiraversion = newv.name
            else:
                missing_versions[jiraversion].add(bug)
                return
        elif(not jiraversion):
            print "[ERROR] No mapping for '" + bug.target_milestone + "'. Please fix the mapping. Bug: " + str(bug)
            return
            
    ## TODO: make this logic more clear.
    ## for now we have the same test twice to aviod None to fall through.
    if (jiraversion and jiraversion != NO_VERSION): 
        fixversion=[{ "name" : jiraversion }]

    ## ensure the product name exists as a component
    global components
    if(not next((c for c in components if bug.product == c.name), None)): 
        comp = jira.create_component(bug.product, ECLIPSE_PROJECT)
        components = jira.project_components(ECLIPSE_PROJECT)


    labels=['bzira']
    labels.append(bug.component)
    if(bug.target_milestone and bug.target_milestone!="---"):
        labels.append(bug.target_milestone.replace(" ", "_")) #labels not allowed to have spaces in it.

    issue_dict = {
        'project' : { 'key': ECLIPSE_PROJECT },
        'summary' : bug.summary + ' [EBZ#' + str(bug.id) + "]",
        'description' : bug.getcomments()[0]['text'], # todo - this loads all comments...everytime. probably should wait to do this once it is absolutely needed.
        'issuetype' : { 'name' : 'Task' }, # No notion of types in bugzilla just taking the most generic/non-specifc in jira
        'priority' : { 'name' : bz_to_jira_priority(options, bug) },
        'labels' :   labels,
        'fixVersions' : fixversion,
        'components' : [{ "name" : bug.product }],
        
    }

    return issue_dict

def map_linuxtools(version):
    #TODO: make this use real neon versions.
    #TODO: curently based on map from xcoulon
    versions = {
        "4.2.1" : "Mars.2 (4.5)",
        "4.2"   : "Mars.2 (4.5)",
        "4.1"   : "Mars.1 (4.5)",
        "4.1.0" : "Mars.1 (4.5)", 
        "4.0"   : "Mars (4.5)",
        "---"   : NO_VERSION
        }
    return versions.get(version, None)

bzprod_version_map = {
    #"WTP Incubator" : (lambda version: NO_VERSION),

    # TODO ensure this works for 3.8.x -> Neon.x 
    "JSDT" : (lambda version: re.sub(r"3.8(.*)", r"Neon (4.6)\1", version)),
    "WTP Source Editing" : (lambda version: re.sub(r"3.8(.*)", r"Neon (4.6)\1", version)),

    # TODO ensure this works for 4.6.x -> Neon.x 
    "Platform" : (lambda version: re.sub(r"4.6(.*)", r"Neon (4.6)\1", version)),

    # 4.2.1 -> Mars.2
    # 5.0.0 -> Neon.?
    "Linux Tools" : map_linuxtools,

    #"m2e" : (lambda version: NO_VERSION)
    
    }


    
def bz_to_jira_version(options, bug):
    """Return corresponding jira version for bug version. None means mapping not known. NO_VERSION means it has no fixversion."""
    bzversion = bug.target_milestone
    b2j = None

    ## '---' corresponds to no version set.
    if (bzversion == "---"):
        return NO_VERSION

    ## Use jira version Future for versions that is tied to no specific version
    if (bzversion == 'Future'):
        return 'Future'
    
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


bz2jira_status = {
           "NEW" : "Open",
           "REOPENED": "Reopened",
           "RESOLVED" : "Resolved",
           "VERIFIED" : "Verified",
           "CLOSED" : "Closed",
           "ASSIGNED" : "Coding In Progress", # is this the right approximation ?
    }
    
def bz_to_jira_status(options, bug):

    jstatusid = None

    if bug.status in bz2jira_status:
        jstatus = bz2jira_status[bug.status]
        jstatusid = next((s for s in statuses if jstatus == s.name), None)

    if(jstatusid):
        return jstatusid

    raise ValueError('Could not find matching status for ' + bug.status)
    
bz2jira_resolution = {
           "FIXED": "Done",
           "INVALID" : "Invalid",
           "WONTFIX" : "Won't Fix",
           "DUPLICATE" : "Duplicate Issue",
           "WORKSFORME" : "Cannot Reproduce Bug",
           "MOVED" : "Migrated to another ITS",
           "NOT_ECLIPSE" : "Invalid" # don't have an exact mapping so using invalid as "best approximation"
    }
    
def bz_to_jira_resolution(options, bug):

    jstatusid = None

    if (bug.resolution == ""):
        return None
    
    if bug.resolution in bz2jira_resolution:
        jresolution = bz2jira_resolution[bug.resolution]
        jresolutionid = next((s for s in resolutions if jresolution == s.name), None)
    elif bug.resolution == "":
        jresolution = "None"
        jresolutionid = next((s for s in resolutions if jresolution == s.name), None)
               
    if(jresolutionid):
        return jresolutionid

    raise ValueError('Could not find matching resolution for ' + bug.resolution)
    
def parse_options():
    usage = "Usage: %prog -u <user> -p <password> \nCreates proxy issues for bugzilla issues in jira"

    parser = OptionParser(usage)
    parser.add_option("-u", "--user", dest="username", help="jira username")
    parser.add_option("-p", "--pwd", dest="password", help="jira password")
    parser.add_option("-s", "--server", dest="jiraserver", default="https://issues.stage.jboss.org", help="Jira instance")
    parser.add_option("-d", "--dry-run", dest="dryrun", action="store_true", help="do everything but actually creating issues")
    parser.add_option("-v", "--verbose", dest="verbose", action="store_true", help="be verbose")
    # TODO should we support min age in hours instead of days? How often do we want to run this script?
    parser.add_option("-m", "--min-age", dest="minimum_age_to_process", help="if set, a limit will put on queries to have it only return results that have changed in the given amount of hours.")
    parser.add_option("-S", "--start-date", dest="start_date", default="", help="use this start date (yyyy-mm-dd) as the threshhold from which to query for bugzillas")

    (options, args) = parser.parse_args()

    if not options.username or not options.password:
        parser.error("Missing username or password")

    return options

def proces(bug, bugs):
    newissue = None

    changeddate = datetime.strptime(str(bug.delta_ts), '%Y%m%dT%H:%M:%S')
    difference = now - changeddate

    if(options.verbose):
        print '[DEBUG] %s - %s [%s, %s, [%s]] {%s} -> %s (%s)' % (bug.id, bug.summary, bug.product, bug.component, bug.target_milestone, bug.delta_ts, bug.weburl, difference)
    else:
        sys.stdout.write('.')
        
    issue_dict = create_proxy_jira_dict(options, bug)

    if(issue_dict):
        proxyissue = lookup_proxy(options, bug)
        
        if(proxyissue):
            if(options.verbose):
                print "[INFO] " + bzserver + str(bug.id) + " already proxied as " + options.jiraserver + "/browse/" + proxyissue['key'] + " checking if something needs updating/syncing."

            fields = {}
            if (not next((c for c in proxyissue['fields']['components'] if bug.product == c['name']), None)):
                #TODO: this check for existence in list of components
                # but then overwrites anything else. Problematic or not ?
                updcomponents = [{"name" : bug.product}]
                fields["components"] = updcomponents

                #TODO: see if fixversions matches, see if status/resolutoin matches?
                
                if len(fields)>0:
                    print "Updating " + proxyissue['key'] + " with " + str(fields)
                    isbug = jira.issue(proxyissue['key'])
                    isbug.update(fields)
                else:
                    print "No detected changes."
        else:
            if(options.verbose):
                print "[INFO] Want to create jira for " + str(bug)
                print "[DEBUG] " + str(issue_dict)
            newissue = jira.create_issue(fields=issue_dict)
            bugs.append(newissue)
            
            ## Setup links
            link = {"object": {'url': bug.weburl, 'title': "Original Eclipse Bug"}}
            print "[INFO] Created " + options.jiraserver + "/browse/" + newissue.key
            jira.add_simple_link(newissue, object=link)

            # Check for transition needed
            jstatus = bz_to_jira_status(options, bug)
            jresolution = bz_to_jira_resolution(options, bug)

            #print ""
            #print "Need to transitiation from " + str(newissue.fields.status) + "/" + str(newissue.fields.resolution) +" to " + str(jstatus.name) + "/" + (str(jresolution.name) if jresolution else '(nothing)')

            transid = (
                 newissue.fields.status.name if newissue.fields.status else None,
                 newissue.fields.resolution.name if newissue.fields.resolution else None,
                 jstatus.name if jstatus else None,
                 jresolution.name if jresolution else None)


            if(transid in transitionmap):
                trans = transitionmap[transid]
                if(trans):
                    #print "Want to do " + str(transid) + " with " + str(trans)
                    #print "Can do: " + str(jira.transitions(newissue))

                    wantedres={ "name": trans["resolution"] } if "resolution" in trans else None
                    #print "Wanted res: " + str(wantedres)

                    try:
                        if(wantedres):
                            jira.transition_issue(newissue, trans["id"],resolution=wantedres)
                        else:
                            jira.transition_issue(newissue, trans["id"])
                    except JIRAError as je:
                        print je
                        jira_failure[newissue.key].add("Could not perform transition" + str(trans) + " error: " + str(je))
                #else:
                    #print "No transition needed"
            else:
                raise ValueError("Do not know how to do transition for " + str(transid) + " with " + str(trans))

    return newissue


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
    last_change_time = now - timedelta(hours=int(options.minimum_age_to_process))
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

    

if(len(issues) > 0):

    print "[INFO] " + "Logging in to " + options.jiraserver
    jira = JIRA(options={'server':options.jiraserver}, basic_auth=(options.username, options.password))

    #TODO: should get these data into something more structured than individual global variables.
    versions = jira.project_versions(ECLIPSE_PROJECT)
    components = jira.project_components(ECLIPSE_PROJECT)

    resolutions = jira.resolutions()
    statuses = jira.statuses()

    if (options.verbose):
        print "[DEBUG] " + "Found " + str(len(components)) + " components and " + str(len(versions)) + " versions in JIRA"

    createdbugs = []

    for bug in issues:
        try:
            proces(bug, createdbugs)
        except ValueError as ve:
            print "[ERROR] Issue when processing " + str(bug) + ". Cannot determine if the bug was created or not. See details above."
            print ve


    ## report issues
    for v,k in missing_versions.iteritems():
        print "Missing version '" + v + "'"
        for b in k:
            print "  " + b.product + ": " + b.weburl
        accept = raw_input("Create " + v + " ?")
        if accept.capitalize() in "Y":
            jira.create_version(v, ECLIPSE_PROJECT)

    for v,k in jira_failure.iteritems():
        print "Jira " + v + " gave following errors:"
        for b in k:
            print "  " + b
            
    # Prompt user to accept new JIRAs or delete them
    if(len(createdbugs)>0): 
        accept = raw_input("Accept " + str(len(createdbugs)) + " created JIRAs? [Y/n] ")
        if accept.capitalize() in ["N"]:
            for b in createdbugs:
                print "[INFO] " + "Delete " + options.jiraserver + "/browse/" + str(b)
                b.delete()
else:
    print "[INFO] No bugzillas found matching the query. Nothing to do."
