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
        return 'None'
    else:
        return str(s)

# thanks to http://guidetoprogramming.com/joomla153/python-scripts/22-send-email-from-python
def mailsend (smtphost, fromEmailAddress, toEmailAddress, subject, message):
    server = smtplib.SMTP(smtphost, 25)
    header = 'To: ' + toEmailAddress + '\n' + \
        'From: ' + fromEmailAddress + '\n' + \
        'Subject: ACTION REQUIRED: ' + subject + '\n\n'
    msg = header + '\n' + message
    #print msg
    server.sendmail(fromEmailAddress, toEmailAddress, msg)
    server.close()

    
def render(issueType, issueDesc, jira_env, issues, jql, options):
        
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
                whoEmail = options.nobodysemail
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


            errortext = "\n" + url + "\n" + \
                "Summary: " + fields['summary'] + "\n\n" + \
                "Assignee: " + whoName + " <" + whoEmail + ">\n" + \
                "Problem: " + issueType + " - " + issueDesc + "\n" + \
                "Last Update: " + str(lastupdate) + "\n\n----------------------------\n\n"

            errortextnode = doc.createTextNode(errortext)
            error.appendChild(errortextnode)

            testcase.appendChild(error)
            testsuite.appendChild(testcase)

            subject = "\n* " + issueType + " for " + jirakey
  
            # load email content into a dict(), indexed by email recipient & JIRA
            if not whoEmail in emailsToSend:
                emailsToSend[whoEmail] = {}
            emailsToSend[whoEmail][jirakey] = subject + '\n' + errortext  

    else:
        testcase = doc.createElement("testcase")
        testcase.setAttribute("classname", issueType)
        testcase.setAttribute("name", "found.noissues")
        testsuite.appendChild(testcase)
 
    print('Write to ' + issueType.lower().replace(" ","") + "-test.xml")
    output = open(issueType.lower().replace(" ","") + "-test.xml", 'w')
    output.write(doc.toprettyxml(indent="  "))

    # send emails & log to file
    log = ''
    if options.fromemail:
        if len(emailsToSend) > 0:
            for i, whoEmail in enumerate(emailsToSend):
                numProblems = str(len(emailsToSend[whoEmail]))
                # note: python uses `value if condition else otherValue`, which is NOT the same as `condition ? value : otherValue`
                entry = "Send email with " + numProblems + " issue(s) to: " + (options.toemail if options.toemail else whoEmail)
                print entry
                log = log + entry + "\n\n"
                message = ''
                for j, jirakey in enumerate(emailsToSend[whoEmail]):
                    message = message + emailsToSend[whoEmail][jirakey]
                    log = log + emailsToSend[whoEmail][jirakey]

                message = "This is a mail based on results from a query (see bottom of email) to locate stalled/invalid jiras. Please fix them. Thanks!\n\n " + message
                message = message + "\n\nQuery used: "  + options.jiraserver + "/issues/?jql=" + urllib.quote_plus(jql) + "\n"
                # send to yourself w/ --toemail override, or else send to actual recipient
                # note: python uses `value if condition else otherValue`, which is NOT the same as `condition ? value : otherValue`
                mailsend (options.smtphost, options.fromemail, (options.toemail if options.toemail else whoEmail), numProblems + ' issue' + ('s' if len(emailsToSend[whoEmail]) > 1 else '') + ' with ' + issueType.lower(), message)
    
    if log:
        output = open(issueType.lower().replace(" ","") + ".log", 'w')
        output.write(log)

usage = "usage: %prog -u <user> -p <password> -r <report.json>\nGenerates junit test report based on issues returned from queries."

parser = OptionParser(usage)
parser.add_option("-u", "--user", dest="username", help="jira username")
parser.add_option("-p", "--pwd", dest="password", help="jira password")
parser.add_option("-s", "--server", dest="jiraserver", default="https://issues.jboss.org", help="Jira instance")
parser.add_option("-r", "--report", dest="reportfile", default=None, help=".json file with list of queries to run")
parser.add_option("-f", "--fromemail", dest="fromemail", default=None, help="email address from which to send mail; if omitted, no mail will be sent")
parser.add_option("-t", "--toemail", dest="toemail", default=None, help="email address to which to send mail; if omitted, send to actual JIRA assignees")
parser.add_option("-n", "--nobodysemail", dest="nobodysemail", default=None, help="email to use when noone is assigned; required if fromemail is specified")
parser.add_option("-m", "--smtphost", dest="smtphost", default=None, help="smtp host to use; required if fromemail is specified")

(options, args) = parser.parse_args()

if not options.username or not options.password:
    parser.error("Missing username or password")

if options.fromemail and (not options.nobodysemail or not options.smtphost):
    parser.error("Need to specify both nobodyemail and smpthost when sending mails")
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
                render(issueType, fields['description'], data, data["issues"], fields['jql'], options)
            else:
                print "No issues found with '" + issueType.lower() + "'"
else:
    print "Generating based on .json found on standard in"
    data = json.load(sys.stdin)
    render('stdin', 'Query from standard in.', data, data["issues"], None, options)

