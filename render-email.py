#!/usr/bin/python

from urlparse import urlparse
import urllib
import urllib2
##import yaml  not on rhel4
import json
import sys
import smtplib
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

# thanks to http://guidetoprogramming.com/joomla153/python-scripts/22-send-email-from-python
def mailsend (fromEmailAddress, toEmailAddress, subject, message):
    server = smtplib.SMTP("smtp.corp.redhat.com", 25)
    header = 'To: ' + toEmailAddress + '\n' + \
        'From: ' + fromEmailAddress + '\n' + \
        'Subject: ACTION REQUIRED: ' + subject + '\n\n'
    msg = header + '\n' + message
    #print msg
    server.sendmail(fromEmailAddress, toEmailAddress, msg)
    server.close()

def render(issueType, issueDesc, jira_env, issues, fromEmailAddress, toEmailAddress):
        
    doc = Document()
    testsuite = doc.createElement("testsuite")
    doc.appendChild(testsuite)

    emailsToSend = {}

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

            o = urlparse(v['self'])
            url = o.scheme + "://" + o.netloc + "/browse/" + jirakey

            lastupdate = datetime.datetime.now() - datetime.datetime.strptime(fields['updated'][:-5], "%Y-%m-%dT%H:%M:%S.%f" ).replace(tzinfo=None)

            subject = "\n* " + issueType + " for " + jirakey

            errortext = "\n" + url + "\n" + \
                "Issue: " + fields['summary'] + "\n\n" + \
                "Assignee: " + whoName + " <" + whoEmail + ">\n" + \
                "Error: " + issueType + " - " + issueDesc + "\n" + \
                "Last Update: " + str(lastupdate) + "\n\n----------------------------\n\n"

            # load email content into a dict(), indexed by email recipient & JIRA
            if not whoEmail in emailsToSend:
                emailsToSend[whoEmail] = {}
            emailsToSend[whoEmail][jirakey] = subject + '\n' + errortext  

    else:
        print('No problems found')

    # send emails & log to file
    log = ''
    if fromEmailAddress:
        if len(emailsToSend) > 0:
            for i, whoEmail in enumerate(emailsToSend):
                numProblems = str(len(emailsToSend[whoEmail]))
                # note: python uses `value if condition else otherValue`, which is NOT the same as `condition ? value : otherValue`
                print "Send email with " + numProblems + " issue(s) to: " + (toEmailAddress if toEmailAddress else whoEmail)
                log = log + "Send email with " + numProblems + " issue(s) to: " + (toEmailAddress if toEmailAddress else whoEmail) + "\n\n"
                message = ''
                for j, jirakey in enumerate(emailsToSend[whoEmail]):
                    message = message + emailsToSend[whoEmail][jirakey]
                    log = log + emailsToSend[whoEmail][jirakey]
                    
                # send to yourself w/ --toemail override, or else send to actual recipient
                # note: python uses `value if condition else otherValue`, which is NOT the same as `condition ? value : otherValue`
                mailsend (fromEmailAddress, (toEmailAddress if toEmailAddress else whoEmail), numProblems + ' JIRA' + ('s' if len(emailsToSend[whoEmail]) > 1 else '') + ' with ' + issueType.lower(), message)

    if log:
        output = open(issueType.lower().replace(" ","") + ".log", 'w')
        output.write(log)

usage = "usage: %prog -u <user> -p <password> -r <report.json>\nGenerates junit test report based on issues returned from queries."

parser = OptionParser(usage)
parser.add_option("-u", "--user", dest="username", help="jira username")
parser.add_option("-p", "--pwd", dest="password", help="jira password")
parser.add_option("-s", "--server", dest="jiraserver", default="https://issues.jboss.org", help="Jira instance")
parser.add_option("-r", "--report", dest="reportfile", default=None, help=".json file with list of queries to run")
parser.add_option("-f", "--fromemail", dest="fromEmailAddress", default=None, help="email address from which to send mail; if omitted, no mail will be sent")
parser.add_option("-t", "--toemail", dest="toEmailAddress", default=None, help="email address to which to send mail; if omitted, send to actual JIRA assignees")
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
                render(issueType, fields['description'], data, data["issues"], options.fromEmailAddress, options.toEmailAddress)
            else:
                print "No issues found with '" + issueType.lower() + "'"
else:
    print "Generating based on .json found on standard in"
    data = json.load(sys.stdin)
    render('stdin', 'Query from standard in.', data, data["issues"], options.fromEmailAddress, options.toEmailAddress)
