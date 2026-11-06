# Fedora release checklist

Use this checklist for every Fedora RPM release.

1. Update `VERSION` in `Makefile`, `Version` in `packaging/fedora/charge-sentinel.spec`, `metadata.json`, and `CHANGELOG.md`.
2. Run the source validation suite:

   ```bash
   make validate
   ```

3. Build the RPM in a Fedora 44 environment:

   ```bash
   make rpm
   make rpm-check
   ```

4. Inspect the resulting RPM:

   ```bash
   rpm -qip build/rpmbuild/RPMS/noarch/charge-sentinel-*.noarch.rpm
   rpm -qlp build/rpmbuild/RPMS/noarch/charge-sentinel-*.noarch.rpm
   ```

5. In a disposable Fedora environment, install the RPM, run `rpm -V charge-sentinel`, and confirm these paths exist:

   ```text
   /usr/libexec/charge-sentinel-helper
   /usr/bin/charge-sentinel-doctor
   /usr/share/gnome-shell/extensions/charge-sentinel@subinz1.github.io
   ```

6. Generate and publish a `SHA256SUMS` asset with the RPM. State clearly whether the RPM is GPG-signed.
7. Create a `vX.Y.Z` Git tag and GitHub Release only after the previous checks pass.
