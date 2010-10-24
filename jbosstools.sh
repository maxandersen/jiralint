#echo From The Build > $WORKSPACE/jlint-test.xml
#cp ~/Documents/code/jlint/jira-cli-4.2/sample.xml sample-test.xml
#echo FIXME: JBIDE-456 is broken because of bad fix. > tasks.txt
#echo FIXME: https://jira.jboss.org/browse/JBDS-34 is even worse >> tasks.txt
cd jira-cli-4.2/
./jira -s https://jira.jboss.org -u ${JIRA_USER} -p ${JIRA_PWD} -r ../testcase-render.py report ToolsIllegalFixVersion > $WORKSPACE/jlint-test.xml

