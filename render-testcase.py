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

def email_array_to_string(email_array):
    email_string = ""
    for name in email_array:
        email_string = email_string + (", " if email_string else "") + name + " <" + email_array[name] + ">"
    return email_string

# thanks to http://guidetoprogramming.com/joomla153/python-scripts/22-send-email-from-python
def mailsend (smtphost, from_email, to_email, subject, message, recipients_list):
    server = smtplib.SMTP(smtphost, 25)

    header = 'To: ' + recipients_list + '\n' + \
        'From: ' + from_email + '\n' + \
        'Subject: ACTION REQUIRED: ' + subject + '\n\n'
    msg = header + '\n' + message
    #print msg
    server.sendmail(from_email, recipients_list, msg)
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
                component_details.append({'name': component_name, 'lead': component_lead_name, 'email': component_lead_email})
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

            recipients = {}
            assignees = {}
            assignee_name = "Nobody"
            assignee_email = str(options.unassignedjiraemail)
            if fields['assignee']:
                assignee_name = str(fields['assignee']['name'])
                assignee_email = str(fields['assignee']['emailAddress'])
                assignees[assignee_name] = assignee_email
                recipients[assignee_name] = assignee_email
                if not assignee_name in email_addresses:
                    email_addresses[assignee_name] = assignee_email

            # TODO handle array of components
            elif component_details:
                for component_detail in component_details:
                    # print component_detail
                    recipients[component_detail['lead']] = component_detail['email']
            else:
                # default assignee - send to mailing list if no component set
                recipients["Nobody"] = str(options.unassignedjiraemail)

            # print recipients

            testcase = doc.createElement("testcase")
            testcase.setAttribute("classname", jira_key)
            testcase.setAttribute("name", issue_type.lower().replace(" ","") + xstr(fix_version) + "." + assignee_name)

            o = urlparse(v['self'])
            url = o.scheme + "://" + o.netloc + "/browse/" + jira_key

            error = doc.createElement("error")

            lastupdate = datetime.datetime.now() - datetime.datetime.strptime(fields['updated'][:-5], "%Y-%m-%dT%H:%M:%S.%f" ).replace(tzinfo=None)

            error.setAttribute("message", "\n* [" + assignee_email + "] " + issue_type + " for " + jira_key)

            component_name = ""
            lead_info = ""
            assignee_info = ""
            if component_details:
                for component_detail in component_details:
                    component_name = component_name + (", " if component_name else "") + component_detail['name']
                    lead_info = lead_info + (", " if lead_info else "") + component_detail['lead'] + " <" + component_detail['email'] + ">"

            assignee_info = email_array_to_string(assignees)
            # print assignee_info

            error_text = "\n" + url + "\n" + \
                "Summary: " + fields['summary'] + "\n\n" + \
                ("Assignee(s): " + assignee_info if assignee_info else "Assignee: None set - please fix.") + "\n" + \
                ("Lead(s): " + lead_info + "\n" if lead_info else "") + \
                ("Component(s): " + component_name if component_name else "Component: None set - please fix.") + "\n" + \
                "Problem: " + issue_type + " - " + issue_description + "\n" + \
                "Last Update: " + str(lastupdate) + "\n\n----------------------------\n\n"

            error_text_node = doc.createTextNode(error_text)
            error.appendChild(error_text_node)

            testcase.appendChild(error)
            testsuite.appendChild(testcase)

            subject = "\n* " + issue_type + " for " + jira_key
  
            # load email content into a dict(), indexed by email recipient & JIRA
            recipient_list = email_array_to_string(recipients)
            if not recipient_list in emails_to_send:
                emails_to_send[recipient_list] = {}
            emails_to_send[recipient_list][jira_key] = {'message': subject + '\n' + error_text, 'recipients': recipient_list}
            # print emails_to_send[recipient_list][jira_key]

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
                    message = message + emails_to_send[assignee_email][jira_key]['message']
                    log = log + emails_to_send[assignee_email][jira_key]['message']
                    # print emails_to_send[assignee_email][jira_key]['recipients']

                # wrap generated message w/ header and footer
                message = "This email is the result of a query to locate stalled/invalid jiras. Please fix them. Thanks!\n\n " + message
                message = message + "\n\nQuery used: "  + options.jiraserver + "/issues/?jql=" + urllib.quote_plus(jql) + "\n"
                # send to yourself w/ --toemail override, or else send to actual recipient
                # note: python uses `value if condition else otherValue`, which is NOT the same as `condition ? value : otherValue`
                mailsend (options.smtphost, 
                    options.fromemail, 
                    (options.toemail if options.toemail else assignee_email), 
                    problem_count + ' issue' + ('s' if len(emails_to_send[assignee_email]) > 1 else '') + ' with ' + issue_type.lower(), 
                    message,
                    emails_to_send[assignee_email][jira_key]['recipients'])
    
    if log:
        output = open(issue_type.lower().replace(" ","") + ".log", 'w')
        output.write(log)

    return email_addresses

usage = "usage: %prog -u <user> -p <password> -r <report.json>\nGenerates junit test report based on issues returned from queries."

parser = OptionParser(usage)
parser.add_option("-u", "--user", dest="username", help="jira username")
parser.add_option("-p", "--pwd", dest="password", help="jira password")
parser.add_option("-s", "--server", dest="jiraserver", default="https://issues.jboss.org", help="Jira instance")
parser.add_option("-l", "--limit", dest="maxresults", default=200, help="maximum number of results to return from json queries (default 200)")
parser.add_option("-r", "--report", dest="reportfile", default=None, help=".json file with list of queries to run")
parser.add_option("-f", "--fromemail", dest="fromemail", default=None, help="email address from which to send mail; if omitted, no mail will be sent")
parser.add_option("-t", "--toemail", dest="toemail", default=None, help="email address override to which to send all mail; if omitted, send to actual JIRA assignees")
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
            payload = {'jql': fields['jql'], 'maxResults' : options.maxresults}
            data = jiraquery(options, "/rest/api/2/search?" + urllib.urlencode(payload))
            print(str(len(data['issues'])) + " issues found with '" + issue_type.lower() + "'")
            email_addresses = render(issue_type, fields['description'], data, data['issues'], fields['jql'], options, email_addresses)
else:
    print "Generating based on .json found on standard in"
    data = json.load(sys.stdin)
    email_addresses = render('stdin', 'Query from standard in.', data, data['issues'], None, options, email_addresses)

