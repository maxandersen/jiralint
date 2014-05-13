from urlparse import urlparse
import urllib
import urllib2
##import yaml  not on rhel4
import json
import sys
import datetime
from datetime import timedelta
## from dateutil.parser import parse not on rhel6
import pprint
from xml.dom.minidom import Document
from optparse import OptionParser

pp = pprint.PrettyPrinter(indent=4)

def xstr(s):
    if s is None:
        return 'nobody'
    else:
        return str(s)
    
def render(issueType, issueDesc, jira_env, issues):
        
    doc = Document()
    testsuite = doc.createElement("testsuite")
    doc.appendChild(testsuite)

    if len(issues) > 0:
        for i, v in enumerate(issues):
            
            fields = v['fields']
            # For available field names, see the variables in
            # src/java/com/atlassian/jira/rpc/soap/beans/RemoteIssue.java 
            #logger.info('%s\t%s\t%s' % (v['key'], v['assignee'], v['summary']))
            # print fields['assignee']
            fixVersion = ""
            for version in fields['fixVersions']:
                fixVersion += '_' + version['name']
            fixVersion = fixVersion[1:]
            if fixVersion == "":
                if issueType == "nofixversion":
                    fixVersion = ""
                else:
                    fixVersion=".nofixversion"
            else:
                fixVersion = "." + xstr(fixVersion)

            if fields['assignee']:
                whoEmail = str(fields['assignee']['emailAddress'])
                whoName  = str(fields['assignee']['name'])
            else:
                whoEmail = "external-exadel-list@redhat.com"
                whoName = "nobody"

            jirakey = v['key']

            testcase = doc.createElement("testcase")
            testcase.setAttribute("classname", jirakey)
            testcase.setAttribute("name", issueType + xstr(fixVersion) + "." + whoName)

            o = urlparse(v['self'])
            url = o.scheme + "://" + o.netloc + "/browse/" + jirakey

            error = doc.createElement("error")

            lastupdate = datetime.datetime.now() - datetime.datetime.strptime(fields['updated'][:-5], "%Y-%m-%dT%H:%M:%S.%f" ).replace(tzinfo=None)

            error.setAttribute("message", "\n* [" + whoEmail + "] " + issueType + " for " + jirakey)

            errortext = doc.createTextNode("\n" + url + "\n" +
                "Issue: " + fields['summary'] + "\n" +
                "Assignee: " + whoName + " <" + whoEmail + ">\n" +
                "Error: " + issueType + " - " + issueDesc + "\n" +
                "Last Update: " + str(lastupdate) + "\n\n----------------------------\n\n")
            error.appendChild(errortext)

            testcase.appendChild(error)
            testsuite.appendChild(testcase)
    else:
        testcase = doc.createElement("testcase")
        testcase.setAttribute("classname", issueType)
        testcase.setAttribute("name", "found.noissues")
        testsuite.appendChild(testcase)
 
    print('Write to ' + issueType.lower().replace(" ","") + "-test.xml")
    output = open(issueType.lower().replace(" ","") + "-test.xml", 'w')
    output.write(doc.toprettyxml(indent="  "))



usage = "usage: %prog -u <user> -p <password> -r <report.json>\nGenerates junit test report based on issues returned from queries."

parser = OptionParser(usage)
parser.add_option("-u", "--user", dest="username", help="jira username")
parser.add_option("-p", "--pwd", dest="password", help="jira password")
parser.add_option("-s", "--server", dest="jiraserver", default="https://issues.jboss.org", help="Jira instance")
parser.add_option("-r", "--report", dest="reportfile", default=None, help=".json file with list of queries to run")
(options, args) = parser.parse_args()

if not options.username or not options.password:
    parser.error("Missing username or password")

if options.reportfile:
    print "Using reports defined in " + options.reportfile
    reports = json.load(open(options.reportfile, 'r'))

    for report in reports:
        for issueType,fields in report.items():
            print("Check for '"  + issueType.lower() + "'")
            authinfo = urllib2.HTTPPasswordMgrWithDefaultRealm()
            authinfo.add_password(None, options.jiraserver, options.username, options.password)
            handler = urllib2.HTTPBasicAuthHandler(authinfo)
            myopener = urllib2.build_opener(handler)
            opened = urllib2.install_opener(myopener)

            payload = {'jql': fields['jql'], 'maxResults' : 1000}
            req = urllib2.Request(options.jiraserver +  "/rest/api/2/search?" + urllib.urlencode(payload))

            data=json.load(urllib2.urlopen(req))
            if len(data["issues"]) > 0:
                print(str(len(data["issues"])) + " issues found with '" + issueType.lower() + "'")
                render(issueType, fields['description'], data, data["issues"])
            else:
                print "No issues found with '" + issueType.lower() + "'"
else:
    print "Generating based on .json found on standard in"
    data = json.load(sys.stdin)
    render('stdin', 'Query from standard in.', data, data["issues"])
