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
def mailsend (smtphost, from_email, to_email, subject, message):
    server = smtplib.SMTP(smtphost, 25)
    header = 'To: ' + to_email + '\n' + \
        'From: ' + from_email + '\n' + \
        'Subject: ACTION REQUIRED: ' + subject + '\n\n'
    msg = header + '\n' + message
    #print msg
    server.sendmail(from_email, to_email, msg)
    server.close()

def jiraquery (options, url):
    authinfo = urllib2.HTTPPasswordMgrWithDefaultRealm()
    authinfo.add_password(None, options.jiraserver, options.username, options.password)
    handler = urllib2.HTTPBasicAuthHandler(authinfo)
    myopener = urllib2.build_opener(handler)
    opened = urllib2.install_opener(myopener)
    # print options.jiraserver + url
    req = urllib2.Request(options.jiraserver +  url)
    return json.load(urllib2.urlopen(req))

def render(issue_type, issue_description, jira_env, issues, jql, options, email_addresses):
        
    doc = Document()
    testsuite = doc.createElement("testsuite")
    doc.appendChild(testsuite)

    emails_to_send = {}

    if len(issues) > 0:
        for i, v in enumerate(issues):
            
            fields = v['fields']
            jira_key = v['key']

            # For available field names, see the variables in
            # src/java/com/atlassian/jira/rpc/soap/beans/RemoteIssue.java 
            #logger.info('%s\t%s\t%s' % (v['key'], v['assignee'], v['summary']))
            # print fields['components']

            component_details = []
            component_lead_name = ""
            component_lead_email = ""
            for component in fields['components']:
                # print component['id']
                # https://issues.jboss.org/rest/api/2/component/12311294
                component_data = jiraquery(options, "/rest/api/2/component/" + component['id'])
                component_name = str(component_data['name'])
                component_lead_name = str(component_data['lead']['name'])
                if component_lead_name in email_addresses:
                    component_lead_email = email_addresses[component_lead_name]
                    #print "Get:1 email_addresses['" + component_lead_name + "'] = " + component_lead_email
                elif component_lead_name:
                    # print component_lead_name
                    # https://issues.jboss.org/rest/api/2/user?username=ldimaggio requires auth and fails with 401, but 
                    # https://issues.jboss.org/rest/api/2/search?jql=%28assignee=ldimaggio%29&maxResults=1 requires no auth
                    payload = {'jql': '(assignee=' + component_lead_name + ')', 'maxResults' : 1}
                    lead_data = jiraquery(options, "/rest/api/2/search?" + urllib.urlencode(payload))
                    for issue in lead_data['issues']:
                        component_lead_email = str(issue['fields']['assignee']['emailAddress'])
                        email_addresses[component_lead_name] = component_lead_email
                        #print "Set:1 email_addresses['" + component_lead_name + "'] = " + component_lead_email
                component_details.append({component_lead_name,component_lead_email})
            fix_version = ""
            for version in fields['fixVersions']:
                fix_version += '_' + version['name']
            fix_version = fix_version[1:]
            if fix_version == "":
                if issue_type == "No fix version":
                    fix_version = ""
                else:
                    fix_version=".nofixversion"
            else:
                fix_version = "." + xstr(fix_version)

            assignee_name = "nobody"
            assignee_email = str(options.unassignedjiraemail)
            if fields['assignee']:
                assignee_name  = str(fields['assignee']['name'])
                if assignee_name in email_addresses:
                    assignee_email = email_addresses[assignee_name]
                    #print "Get:0 email_addresses['" + assignee_name + "'] = " + assignee_email
                else:
                    assignee_email = str(fields['assignee']['emailAddress'])
                    email_addresses[assignee_name] = assignee_email
                    #print "Set:0 email_addresses['" + assignee_name + "'] = " + assignee_email
            # TODO handle array of components
            elif component_details:
                print jira_key + ": " + str(component_details)
                # assignee_email = component_lead_email
                # assignee_name = component_lead_name

            testcase = doc.createElement("testcase")
            testcase.setAttribute("classname", jira_key)
            testcase.setAttribute("name", issue_type.lower().replace(" ","") + xstr(fix_version) + "." + assignee_name)

            o = urlparse(v['self'])
            url = o.scheme + "://" + o.netloc + "/browse/" + jira_key

            error = doc.createElement("error")

            lastupdate = datetime.datetime.now() - datetime.datetime.strptime(fields['updated'][:-5], "%Y-%m-%dT%H:%M:%S.%f" ).replace(tzinfo=None)

            error.setAttribute("message", "\n* [" + assignee_email + "] " + issue_type + " for " + jira_key)


            error_text = "\n" + url + "\n" + \
                "Summary: " + fields['summary'] + "\n\n" + \
                "Assignee: " + assignee_name + " <" + assignee_email + ">\n" + \
                "Lead: " + component_lead_name + " <" + component_lead_email + ">\n" + \
                "Problem: " + issue_type + " - " + issue_description + "\n" + \
                "Component: " + component_name + "\n" + \
                "Last Update: " + str(lastupdate) + "\n\n----------------------------\n\n"

            error_text_node = doc.createTextNode(error_text)
            error.appendChild(error_text_node)

            testcase.appendChild(error)
            testsuite.appendChild(testcase)

            subject = "\n* " + issue_type + " for " + jira_key
  
            # load email content into a dict(), indexed by email recipient & JIRA
            if not assignee_email in emails_to_send:
                emails_to_send[assignee_email] = {}
            emails_to_send[assignee_email][jira_key] = {subject + '\n' + error_text}

    else:
        testcase = doc.createElement("testcase")
        testcase.setAttribute("classname", issue_type)
        testcase.setAttribute("name", "found.noissues")
        testsuite.appendChild(testcase)
 
    print('Write to ' + issue_type.lower().replace(" ","") + "-test.xml")
    output = open(issue_type.lower().replace(" ","") + "-test.xml", 'w')
    output.write(doc.toprettyxml(indent="  "))

    # send emails & log to file
    log = ''
    if options.fromemail:
        if len(emails_to_send) > 0:
            for i, assignee_email in enumerate(emails_to_send):
                problem_count = str(len(emails_to_send[assignee_email]))
                # note: python uses `value if condition else otherValue`, which is NOT the same as `condition ? value : otherValue`
                entry = "Send email with " + problem_count + " issue(s) to: " + (options.toemail if options.toemail else assignee_email)
                print entry
                log = log + entry + "\n\n"
                message = ''
                for j, jira_key in enumerate(emails_to_send[assignee_email]):
                    message = message + emails_to_send[assignee_email][jira_key]
                    log = log + emails_to_send[assignee_email][jira_key]

                message = "This is a mail based on results from a query (see bottom of email) to locate stalled/invalid jiras. Please fix them. Thanks!\n\n " + message
                message = message + "\n\nQuery used: "  + options.jiraserver + "/issues/?jql=" + urllib.quote_plus(jql) + "\n"
                # send to yourself w/ --toemail override, or else send to actual recipient
                # note: python uses `value if condition else otherValue`, which is NOT the same as `condition ? value : otherValue`
                mailsend (options.smtphost, options.fromemail, (options.toemail if options.toemail else assignee_email), problem_count + ' issue' + ('s' if len(emails_to_send[assignee_email]) > 1 else '') + ' with ' + issue_type.lower(), message)
    
    if log:
        output = open(issue_type.lower().replace(" ","") + ".log", 'w')
        output.write(log)

    return email_addresses

usage = "usage: %prog -u <user> -p <password> -r <report.json>\nGenerates junit test report based on issues returned from queries."

parser = OptionParser(usage)
parser.add_option("-u", "--user", dest="username", help="jira username")
parser.add_option("-p", "--pwd", dest="password", help="jira password")
parser.add_option("-s", "--server", dest="jiraserver", default="https://issues.jboss.org", help="Jira instance")
parser.add_option("-r", "--report", dest="reportfile", default=None, help=".json file with list of queries to run")
parser.add_option("-f", "--fromemail", dest="fromemail", default=None, help="email address from which to send mail; if omitted, no mail will be sent")
parser.add_option("-t", "--toemail", dest="toemail", default=None, help="email address to which to send mail; if omitted, send to actual JIRA assignees")
parser.add_option("-n", "--unassignedjiraemail", dest="unassignedjiraemail", default=None, help="email to use for unassigned JIRAs; required if fromemail is specified")
parser.add_option("-m", "--smtphost", dest="smtphost", default=None, help="smtp host to use; required if fromemail is specified")

(options, args) = parser.parse_args()

if not options.username or not options.password:
    parser.error("Missing username or password")

if options.fromemail and (not options.unassignedjiraemail or not options.smtphost):
    parser.error("Need to specify both --unassignedjiraemail and --smpthost to send mail")
if options.reportfile:
    print "Using reports defined in " + options.reportfile
    reports = json.load(open(options.reportfile, 'r'))

    # store an array of username : email_address we can use as a lookup table
    email_addresses = {}

    for report in reports:
        for issue_type,fields in report.items():
            print("Check for '"  + issue_type.lower() + "'")
            payload = {'jql': fields['jql'], 'maxResults' : 1000}
            data = jiraquery(options, "/rest/api/2/search?" + urllib.urlencode(payload))
            print(str(len(data['issues'])) + " issues found with '" + issue_type.lower() + "'")
            email_addresses = render(issue_type, fields['description'], data, data['issues'], fields['jql'], options, email_addresses)
else:
    print "Generating based on .json found on standard in"
    data = json.load(sys.stdin)
    email_addresses = render('stdin', 'Query from standard in.', data, data['issues'], None, options, email_addresses)

