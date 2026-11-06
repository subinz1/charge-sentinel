Name:           charge-sentinel
Version:        0.1.1
Release:        1%{?dist}
Summary:        GNOME Quick Settings battery charge protection

License:        MIT
URL:            https://github.com/subinz1/charge-sentinel
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  glib2
BuildRequires:  python3
Requires:       gnome-shell >= 50
Requires:       glib2
Requires:       polkit
Requires:       python3

%global extension_uuid charge-sentinel@subinz1.github.io
%global extension_dir %{_datadir}/gnome-shell/extensions/%{extension_uuid}

%description
Charge Sentinel adds a battery-protection tile to GNOME Quick Settings on
supported Fedora laptops. It detects hardware-backed charge thresholds and
uses a narrowly scoped Polkit helper to apply validated settings.

%prep
%autosetup

%build

%install
install -d %{buildroot}%{extension_dir}/schemas
install -p -m 0644 metadata.json extension.js prefs.js %{buildroot}%{extension_dir}/
install -p -m 0644 schemas/org.gnome.shell.extensions.charge-sentinel.gschema.xml %{buildroot}%{extension_dir}/schemas/
glib-compile-schemas %{buildroot}%{extension_dir}/schemas

install -D -p -m 0755 src/charge-sentinel-helper.py %{buildroot}%{_libexecdir}/charge-sentinel-helper
install -D -p -m 0644 src/charge_sentinel_capabilities.py %{buildroot}%{_libexecdir}/charge_sentinel_capabilities.py
install -D -p -m 0755 src/charge-sentinel-doctor.py %{buildroot}%{_bindir}/charge-sentinel-doctor
install -D -p -m 0644 polkit/io.github.subinz1.charge-sentinel.policy %{buildroot}%{_datadir}/polkit-1/actions/io.github.subinz1.charge-sentinel.policy

%check
glib-compile-schemas --strict --dry-run schemas
python3 -m unittest discover -s tests -v

%files
%license LICENSE
%doc README.md CHANGELOG.md docs/platform-support.md docs/release-checklist.md
%{extension_dir}/metadata.json
%{extension_dir}/extension.js
%{extension_dir}/prefs.js
%dir %{extension_dir}/schemas
%{extension_dir}/schemas/org.gnome.shell.extensions.charge-sentinel.gschema.xml
%{extension_dir}/schemas/gschemas.compiled
%attr(0755,root,root) %{_libexecdir}/charge-sentinel-helper
%{_libexecdir}/charge_sentinel_capabilities.py
%attr(0755,root,root) %{_bindir}/charge-sentinel-doctor
%{_datadir}/polkit-1/actions/io.github.subinz1.charge-sentinel.policy

%changelog
* Thu Nov 06 2026 Charge Sentinel contributors - 0.1.1-1
- Harden threshold writes, diagnostics, and RPM verification

* Thu Nov 05 2026 Charge Sentinel contributors - 0.1.0-1
- Initial Fedora RPM release
