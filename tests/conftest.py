import pytest
import hglib
import uuid
import os
import sys
import logging
import pathlib
import shutil
import json
from git import Repo

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.DEBUG)
format = '[%(asctime)s.%(msecs)03d] [%(name)s] [%(levelname)s] ' \
         '%(message)s'

formatter = logging.Formatter(format, '%Y-%m-%d %H:%M:%S')

cons_handler = logging.StreamHandler(sys.stdout)
cons_handler.setFormatter(formatter)
LOGGER.addHandler(cons_handler)


# A class for simulating mercurial backend
class MercurialAppLayoutFixture(object):
    def __init__(self, versions, remote_versions):
        self.versions_root_path = versions.strpath
        self.remote_versions_root_path = remote_versions.strpath
        self.base_versions_dir_path = versions.dirname

        client = hglib.init(
            dest=self.remote_versions_root_path
        )
        client.close()

        self._mercurial_backend = hglib.clone(
            '{0}'.format(self.remote_versions_root_path),
            '{0}'.format(self.versions_root_path)
        )

        self._repos = {}

    def __del__(self):
        self._mercurial_backend.close()

        for val in self._repos.values():
            shutil.rmtree(val['path'])

    def create_repo(self, repo_name, repo_type):
        path = os.path.join(self.base_versions_dir_path, repo_name)

        if repo_type == 'mercurial':
            client = hglib.init(dest=path)
            client.close()
        elif repo_type == 'git':
            repo = Repo.init(path=path)
            repo.close()
        else:
            raise RuntimeError('Unknown repository type provided')

        self._repos[repo_name] = {
            'path': path,
            'type': repo_type,
        }

    def write_file(self, repo_name, file_relative_path, content):
        if repo_name not in self._repos:
            raise RuntimeError('repo {0} not found'.format(repo_name))

        path = os.path.join(
            self._repos[repo_name]['path'], file_relative_path
        )
        dir_path = os.path.dirname(path)

        if not os.path.isfile(path):
            pathlib.Path(dir_path).mkdir(parents=True, exist_ok=True)

            with open(path, 'w') as f:
                f.write(content)

            if self._repos[repo_name]['type'] == 'mercurial':
                client = hglib.open(self._repos[repo_name]['path'])
                client.add(path.encode())
                client.commit('Added file {0}'.format(path))
                self._repos[repo_name]['changesets'] = {
                    'hash': client.log(branch='default')[0][1].decode('utf-8'),
                    'vcs_type': 'mercurial'
                }
            else:
                client = Repo(self._repos[repo_name]['path'])
                client.index.add([self._repos[repo_name]['path']])
                client.index.commit('Added file {0}'.format(path))
                self._repos[repo_name]['changesets'] = {
                    'hash': client.head.commit.hexsha,
                    'vcs_type': 'git'
                }
        else:
            with open(path, 'w') as f:
                f.write(content)

            if self._repos[repo_name]['type'] == 'mercurial':
                client = hglib.open(self._repos[repo_name]['path'])
                client.commit('Modified file {0}'.format(path))
                self._repos[repo_name]['changesets'] = {
                    'hash': client.log(branch='default')[0][1].decode('utf-8'),
                    'vcs_type': 'mercurial'
                }
            else:
                client = Repo(self._repos[repo_name]['path'])
                client.index.commit('Added file {0}'.format(path))
                self._repos[repo_name]['changesets'] = {
                    'hash': client.head.commit.hexsha,
                    'vcs_type': 'git'
                }

        client.close()

    def get_repo_type(self, repo_name):
        if repo_name not in self._repos:
            raise RuntimeError('repo {0} not found'.format(repo_name))

        return self._repos[repo_name]['changesets']['vcs_type']

    def get_changesets(self, repo_name):
        if repo_name not in self._repos:
            raise RuntimeError('repo {0} not found'.format(repo_name))

        return self._repos[repo_name]['changesets']

    def remove_app_version_file(self, app_version_file_path):
        client = hglib.open(self.versions_root_path)
        client.remove(app_version_file_path.encode('utf8'))
        client.commit('Manualy removed file {0}'.format(app_version_file_path))
        client.push()
        client.close()

    def add_version_info_file(
            self,
            version_info_file_path,
            custom_version=None,
            custom_repos=None):
        if custom_repos is None and custom_version is None:
            return

        with open(version_info_file_path, 'w+') as f:
            if custom_version is not None:
                f.write('version = {0}\n'.format(custom_version))
            if custom_repos is not None:
                f.write('repos = {0}\n'.format(json.dumps(custom_repos)))

        client = hglib.open(self.versions_root_path)

        client.add(version_info_file_path)
        client.commit(
            message='Manually add version_info file',
            user='version_manager',
            include=version_info_file_path,
        )

        client.push()
        client.close()

    def create_mercurial_backend_params(self,
                                 app_name,
                                 release_mode='debug',
                                 starting_version='0.0.0.0',
                                 main_system_name=None,
                                 version_template='{0}.{1}.{2}'):
        params = {
            'repos_path': self.base_versions_dir_path,
            'release_mode': release_mode,
            'app_name': app_name,
            'starting_version': starting_version,
            'main_system_name': main_system_name,
            'version_template': version_template,
        }

        if main_system_name is None:
            params['app_version_file'] = '{0}/apps/{1}/version.py'.format(
                self.versions_root_path,
                app_name
            )
        else:
            params['main_version_file'] = '{0}/apps/{1}/main_version.py'.format(
                self.versions_root_path,
                main_system_name
            )
            params['app_version_file'] = '{0}/apps/{1}/{2}/version.py'.format(
                self.versions_root_path,
                main_system_name,
                app_name
            )

        return params


@pytest.fixture(scope='session')
def session_uuid():
    return uuid.uuid4()


@pytest.fixture(scope='function')
def mercurial_app_layout(tmpdir):
    versions = tmpdir.mkdir('versions')
    remote_versions = tmpdir.mkdir('remote_versions')
    app_layout = MercurialAppLayoutFixture(versions, remote_versions)

    yield app_layout

    del app_layout
