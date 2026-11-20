# sanshain-conan

The Conan client of the Sanshain Service. What a producer, a consumer, a provide, a require,
a version, a stability or a stream is, the service decides: see the
[glossary of sanshain-service](https://github.com/paxel/sanshain-service/blob/summer/CONTEXT.md).
The terms below are the client's own.

## Language

**Command**:
The program `sanshain-conan` with its commands `provide`, `require` and `catalog`, installed
with the PyPI package of the same name.
_Avoid_: CLI tool, binary, script

**Helper**:
The class `Sanshain` a project's `conanfile.py` imports from `sanshainconan` and calls in
`generate()`. It does what the command does, reads the environment where the command reads
flags, and reports through Conan's output.
_Avoid_: Plugin, extension, recipe, python_requires

**Strict mode**:
Missing configuration, an unknown field in `sanshain.yaml`, an unfilled placeholder or a
warning of the service fails the call instead of being printed and skipped. Set by `strict`
in the file.
_Avoid_: Hard mode, fail-fast

**Best effort**:
A failure is printed as a warning and the build goes on, so that it does not stop because
the service is away. Set by `--best-effort`, `SANSHAIN_BEST_EFFORT` or `bestEffort` in the
file; the helper reads only the file. Where it meets strict mode is listed on the Conan
client page of the Sanshain site.
_Avoid_: Soft fail, lenient mode, ignore errors

**Puzzled cat**:
The notice printed once when `sanshain.yaml` holds fields no Sanshain client knows. Under
strict mode the call fails after printing it.
_Avoid_: Unknown-field warning, lint

**Warning**:
A line the service sent in a `Sanshain-Warning` response header. The command prints each
one, the helper hands it to Conan's output; under strict mode the call fails after them.
_Avoid_: Notice, message, log line

**Placeholder**:
`{{NAME}}` in the value of an annotation in `sanshain.yaml`, filled from `--set NAME=value`
or the environment variable `SANSHAIN_SET_NAME`. An annotation with an unfilled placeholder
is left out with a warning of the client.
_Avoid_: Variable, template, macro

**Origin**:
Where a build came from, sent with a provide: the build URL, the change URL, tickets and a
note, from flags or `SANSHAIN_` variables. The two URLs are also read from the CI runner's
own variables; nothing is read from git.
_Avoid_: Metadata, build info, provenance (that is the release's attestation)

**State file**:
`.sanshain-cache/state.json` under the directory the command runs in. It holds the ETag of
every require, so that an endpoint the service has not changed is not downloaded again. The
helper keeps none.
_Avoid_: Cache, lockfile, database
