
"""Help script to generate and compile modules."""

from subprocess import call
import os
import sys
import shutil
import logging
import pprint

pch = "Private/UnrealPyPrivatePCH.h"
global unreal_base
unreal_base = os.environ.get('UE_PATH')
if not unreal_base:
    raise Exception(
        'UE_PATH env var need to point to UnrealEngine root directory.')
build_dir_base = os.path.join(
    unreal_base, 'Engine\\Source\\Editor\\UnrealPy\\Private\\')

global python_base
python_base = os.environ.get('PYTHON_BASE')
if not python_base:
    raise Exception(
        'PYTHON_BASE env var need to point to Python 2.7 root directory')

##

global platform
if sys.platform == 'win32':
    platform = {
        'script_ext': '.bat',
        'dynamic_library_ext': '.dll',
        'library_ext': '.lib',
        'unreal_name': 'Win64',
        'build_script': 'Build.bat',
        'python_lib_name': 'python27'
    }
elif sys.platform == 'darwin':
    platform = {
        'script_ext': '.sh',
        'dynamic_library_ext': '.dylib',
        'library_ext': '.a',
        'unreal_name': 'Mac',
        'build_script': os.path.join('Mac', 'Build.sh'),
        'python_lib_name': 'libpython2.7'
    }
else:
    raise Exception('{0} not yet configured, feel free to add. :)'.format(
        sys.platform))


def generate_project_files():
    generate_script = os.path.join(
        unreal_base, 'GenerateProjectFiles' + platform['script_ext'])
    os.chdir(unreal_base)
    if call([generate_script]) != 0:
        raise Exception('Generate Unreal project files failed')


def build_unreal():
    ue_config = 'Debug'
    build_script = os.path.join(
        unreal_base, 'Engine', 'Build', 'BatchFiles', platform['build_script'])
    print(build_script)
    logging.info("Running {0} with args: {1}".format(
        build_script, pprint.pformat(['UE4Editor', platform['unreal_name'], ue_config])))
    if call([build_script, 'UE4Editor', platform['unreal_name'], ue_config]) != 0:
        raise Exception('Unreal build failed')


def build_file_contents(module_name):
    python_include_path = os.path.join(python_base, 'include')
    python_lib_path = os.path.join(python_base, 'lib')
    python_lib = os.path.join(python_base, 'lib', '{0}{1}'.format(
        platform['python_lib_name'], platform['dynamic_library_ext']))
    return """// This file is generated by build.py and edits will be overwritten

using UnrealBuildTool;
using System.Diagnostics;
using System.IO;

public class {module_name} : ModuleRules
{{
    public {module_name}(TargetInfo Target)
    {{
        PublicIncludePaths.Add("Editor/UnrealEd/Public");

        PrivateDependencyModuleNames.AddRange(
            new string[] {{
                "Core",
                "CoreUObject",
                "Engine",
                "UnrealEd",
            }}
        );

        PrivateIncludePaths.Add("{python_include_path}");

        PublicLibraryPaths.Add("{python_lib_path}");
        PublicAdditionalLibraries.Add("{python_lib}");
    }}
}}
""".format(
        module_name=module_name,
        python_include_path=python_include_path,
        python_lib_path=python_lib_path,
        python_lib=python_lib)

pch_contents = """// This file is generated by build.py and edits will be overwritten

#pragma warning (disable:4510)
#pragma warning (disable:4610)
#pragma warning (disable:4146)
"""

##

# currently there is no support for nested modules, all modules need to be leaf
# this should not be too hard to fix, however


class UnrealPyModule(object):

    def __init__(self, name):
        # name arg is like 'unreal.platform.math', but we call ourselves 'math'
        self.name = name.rsplit('.', 1)[-1]
        self.path = os.path.dirname(name.replace('.', '/'))
        self.unreal_name = 'UnrealPy_{0}'.format("{0}_{1}".format(self.path.replace(
            'unreal/', '').replace('/', ' ').title().replace(' ', '_'), self.name.title()))
        self.unreal_module_dir = os.path.join(
            unreal_base, 'Engine', 'Source', 'Editor', self.unreal_name)
        self.unreal_module_dir_private = os.path.join(
            self.unreal_module_dir, 'Private')
        self.pch = 'Private/{0}PrivatePCH.h'.format(self.unreal_name)
        self.library_file = os.path.join(
            self.path, self.name + platform['dynamic_library_ext'])
        self.cython_output_file = os.path.join(
            self.unreal_module_dir_private, self.name.title() + '.cpp')

    def clean(self):
        if os.path.exists(self.unreal_module_dir):
            shutil.rmtree(self.unreal_module_dir)
        if os.path.exists(self.library_file):
            os.remove(self.library_file)

    def build(self):
        self.clean()
        self.emit_cython()
        self.create_unreal_module()

    def emit_cython(self):
        pyx_path = None
        primary_pyx_path = pyx_path = os.path.join(self.path, self.name + '.pyx')
        secondary_pyx_path = os.path.join(self.path, self.name, self.name + '.pyx')
        if os.path.exists(primary_pyx_path):
            pyx_path = primary_pyx_path
        else:
            pyx_path = secondary_pyx_path
        if not os.path.exists(pyx_path):
            raise Exception(
                'Expected to find pyx file at {0} or {1}'.format(primary_pyx_path, secondary_pyx_path))
        if not os.path.exists(self.unreal_module_dir_private):
            os.makedirs(self.unreal_module_dir_private)
        try:
            if call(['cython', '--verbose', '--cplus', '-o', self.cython_output_file, pyx_path]) != 0:
                raise Exception(
                    "cython command exited with non-zero status for {0}".format(self.name))
        except OSError, e:
            logging.error('Is cython installed and on path?')
            raise e
        self.process_cython_output()

    def process_cython_output(self):
        lines = []
        with open(self.cython_output_file) as fin:
            for line in fin:
                lines.extend([line])

        with open(self.cython_output_file, "w") as fout:
            fout.write("\n#include \"{0}\"\n\n".format(self.pch))
            for line in lines:
                fout.write(line)

    def create_unreal_module(self):
        build_file_path = os.path.join(
            self.unreal_module_dir, '{0}.Build.cs'.format(self.unreal_name))
        shutil.copyfile(os.path.join(
            'Modules', '{0}.Build.cs'.format(self.unreal_name)), build_file_path)
        self.add_to_editor_target()
        self.create_pch()

    def add_to_editor_target(self):
        editor_target_path = os.path.join(
            unreal_base, 'Engine', 'Source', 'UE4Editor.Target.cs')
        target_lines = []
        marker_found = False
        with open(editor_target_path, 'r') as fread:
            for line in fread:
                if marker_found:
                    target_lines.extend([line])
                    continue
                else:
                    target_lines.extend([line])
                    if "@UNREALPY@" in line:
                        marker_found = True
                        target_lines.extend(
                            ["OutExtraModuleNames.Add(\"{0}\");\n".format(self.unreal_name)])
        with open(editor_target_path, 'w') as fwrite:
            fwrite.write("".join(target_lines))

    def create_pch(self):
        with open(os.path.join(self.unreal_module_dir, self.pch), 'w') as f:
            f.write(pch_contents)

##


def is_cython_output(file):
    with open(file) as f:
        for i, line in enumerate(f):
            if i > 10:
                break
            if line.startswith('/* Generated by Cython'):
                return True
    return False

##


def clean_cython_output():
    for root, dirs, files in os.walk(build_dir_base):
        for file in files:
            file_path = os.path.join(root, file)
            if file.endswith(".cpp") and is_cython_output(file_path):
                print("Cleaning {0}".format(file_path))
                os.remove(file_path)
                try:
                    os.rmdir(root)
                    print("Removed empty dir {0}".format(root))
                except OSError, e:
                    pass

##


def process_cython_output(file):
    lines = []
    with open(file) as fin:
        for line in fin:
            lines.extend([line])

    with open(file, "w") as fout:
        fout.write("\n#include \"{0}\"\n\n".format(pch))
        for line in lines:
            fout.write(line)

##


def build_cython():
    clean_cython_output()
    for root, dirs, files in os.walk("."):
        for file in files:
            if file.endswith(".pyx") and file == "unreal.pyx":
                file_path = os.path.join(root, file)
                build_dir = os.path.join(build_dir_base, root)
                file_name, file_ext = os.path.splitext(file)
                build_file = os.path.join(build_dir, file_name) + ".cpp"
                if not os.path.exists(build_dir):
                    os.makedirs(build_dir)
                if call(['cython', '--cplus', '-o', build_file, file_path]) != 0:
                    raise Exception('cython command failed')
                process_cython_output(build_file)


def clean_unreal_editor_target():
    editor_target_path = os.path.join(
        unreal_base, 'Engine', 'Source', 'UE4Editor.Target.cs')
    target_lines = []
    marker_found = False
    end_marker_found = False
    with open(editor_target_path, 'r') as fread:
        for line in fread:
            if end_marker_found or not marker_found:
                target_lines.extend([line])
                if "@UNREALPY@" in line:
                    marker_found = True
            elif marker_found and "@/UNREALPY@" in line:
                end_marker_found = True
                target_lines.extend([line])
    with open(editor_target_path, 'w') as fwrite:
        fwrite.write("".join(target_lines))
    if not marker_found or not end_marker_found:
        raise Exception(
            "Unable to work with UE4Editor.Target.cs. You need to manually add the following lines somewhere in SetupBinaries(...) among the OutExtraModuleNames.Add(...) calls:\n// @UNREALPY@\n// @/UNREALPY@")


def build_unreal_old():
    script_file = None
    script_ext = None
    ue_config = 'Debug'
    ue_platform = None
    lib_ext = None
    pylib_name = 'unreal'
    binaries_dir = os.path.join(unreal_base, 'Engine', 'Binaries')

    if sys.platform == 'win32':
        ue_platform = 'Win64'
        script_ext = '.bat'
        script_file = os.path.join('Build' + script_ext)
        lib_ext = '.dll'
    elif sys.platform == 'darwin':
        ue_platform = 'Mac'
        script_file = os.path.join('Mac', 'Build' + script_ext)
        script_ext = '.sh'
        lib_ext = '.dylib'
    else:
        raise Exception("{0} not yet configured for, feel free. :)".format(
            sys.platform))

    lib_name = None
    if ue_config == 'Debug':
        lib_name = 'UE4Editor-UnrealPy-{0}-Debug{1}'.format(
            ue_platform, lib_ext)
    else:
        lib_name = 'UE4Editor-UnrealPy-{0}{1}'.format(ue_platform, lib_ext)

    generate_script = os.path.join(
        unreal_base, 'GenerateProjectFiles' + script_ext)
    build_script = os.path.join(
        unreal_base, 'Engine', 'Build', 'BatchFiles', script_file)

    os.chdir(unreal_base)
    if call([generate_script]) != 0:
        raise Exception('Generate Unreal project files failed')
    if call([build_script, 'UE4Editor', ue_platform, ue_config]) != 0:
        raise Exception('Unreal build failed')

    lib_path = os.path.join(binaries_dir, ue_platform, lib_name)
    if os.path.exists(lib_path):
        lib_dir = os.path.dirname(lib_path)
        pylib_path = os.path.join(lib_dir, pylib_name + '.so')
        if sys.platform == 'win32':
            pylib_path = os.path.join(lib_dir, pylib_name + '.pyd')
        if os.path.exists(pylib_path):
            os.remove(pylib_path)
        os.rename(lib_path, pylib_path)


if __name__ == "__main__":
    clean_unreal_editor_target()

    m = UnrealPyModule('unreal.asset_registry')
    m.build()

    generate_project_files()
    build_unreal()
