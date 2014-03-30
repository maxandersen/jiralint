from urlparse import urlparse
import urllib
import urllib2
##import yaml
import json
import sys
import datetime
from datetime import timedelta
from dateutil.parser import parse
import pprint
from xml.dom.minidom import Document
from optparse import OptionParser

pp = pprint.PrettyPrinter(indent=4)

def xstr(s):
    if s is None:
        return 'None'
    else:
        return str(s)
    
def render(name, desc, jira_env, issues):
        
    doc = Document()
    testsuite = doc.createElement("testsuite")
    doc.appendChild(testsuite)

    if len(issues) > 0:
        for i, v in enumerate(issues):
            
            fields = v['fields']
            # For available field names, see the variables in
            # src/java/com/atlassian/jira/rpc/soap/beans/RemoteIssue.java 
            #logger.info('%s\t%s\t%s' % (v['key'], v['assignee'], v['summary']))
            #  print v
            fixVersion = ""
            for version in fields['fixVersions']:
                fixVersion += '_' + version['name']

            testcase = doc.createElement("testcase")
            testcase.setAttribute("classname", name)
            testcase.setAttribute("name", name + "." + v['key'] + xstr(fixVersion) + "_" + xstr(fields['assignee']))

            o = urlparse(v['self'])
            url = o.scheme + "://" + o.netloc + "/browse/" + v['key']

            error = doc.createElement("error")

            
            #lastupdate = datetime.datetime.now() - parse(fields['updated']).replace(tzinfo=None)
            #error.setAttribute("message", url + " (last update: " + str(lastupdate) + ") -> " + desc)
            error.setAttribute("message", url + " (last update: " + fields(lastupdate) + ") -> " + desc)
            errortext = doc.createTextNode(v['key'] + ": " + fields['summary'] + "(" + url + ")" )
            error.appendChild(errortext)

            testcase.appendChild(error)
            testsuite.appendChild(testcase)
    else:
        testcase = doc.createElement("testcase")
        testcase.setAttribute("classname", name)
        testcase.setAttribute("name", "found.noissues")
        testsuite.appendChild(testcase)
        
    print('Writing to ' + name)
    output = open(name, 'w')
    output.write(doc.toprettyxml(indent="  "))



usage = "usage: %prog -u <user> -p <password> \nGenerates junit test report based on issues returned from queries."

parser = OptionParser(usage)
parser.add_option("-u", "--user", dest="username", help="jira username")
parser.add_option("-p", "--pwd", dest="password", help="jira password")
parser.add_option("-s", "--server", dest="jiraserver", default="https://issues.jboss.org", help="Jira instance")

(options, args) = parser.parse_args()

if not options.username or not options.password or not options.jiraserver:
    parser.error("Need to specify all")

reports = yaml.load(open("reports.yaml", 'r'))

jiraserver = "https://issues.jboss.org"
for report in reports:
    for name,fields in report.items():
        print("Running "  + name)
        
        
        authinfo = urllib2.HTTPPasswordMgrWithDefaultRealm()
        authinfo.add_password(None, options.jiraserver, options.username, options.password)
        handler = urllib2.HTTPBasicAuthHandler(authinfo)
        myopener = urllib2.build_opener(handler)
        opened = urllib2.install_opener(myopener)

        payload = {'jql': fields['jql'], 'maxResults' : 1000}
        req = urllib2.Request(options.jiraserver +  "/rest/api/2/search?" + urllib.urlencode(payload))

        data=json.load(urllib2.urlopen(req))
        print("Generating " + name + " with " + str(len(data["issues"])) + " issues")
        render(name + "-test.xml", fields['description'], data, data["issues"])
