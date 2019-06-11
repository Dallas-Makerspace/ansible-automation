# ansible-automation
Automation for DMS


## Branching strategy

Pull requests would only be accepted into other branches based accepted semversion tags from master while master would hold all changes and code.

For example; one would like to change inventory items in a site. They would update site/${site}.yml with the change and push this to master, Then a release tag created and a pull request submitted to have it pushed into the environment.
