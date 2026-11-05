import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
import Gtk from 'gi://Gtk';

import {ExtensionPreferences} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

function thresholdRow(title, subtitle, lower, upper) {
    return new Adw.SpinRow({
        title,
        subtitle,
        adjustment: new Gtk.Adjustment({
            lower,
            upper,
            step_increment: 1,
            page_increment: 5,
        }),
    });
}

export default class ChargeSentinelPreferences extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        const settings = this.getSettings();
        const page = new Adw.PreferencesPage({
            title: 'Charge Sentinel',
            icon_name: 'battery-good-symbolic',
        });
        window.add(page);

        const limitsGroup = new Adw.PreferencesGroup({
            title: 'Custom charge limits',
            description: 'Use Apply custom limits from Quick Settings after changing these values.',
        });
        page.add(limitsGroup);

        const startRow = thresholdRow(
            'Start charging below',
            'The charger resumes when the battery drops below this percentage.',
            1,
            99,
        );
        settings.bind('custom-start', startRow, 'value', Gio.SettingsBindFlags.DEFAULT);
        limitsGroup.add(startRow);

        const endRow = thresholdRow(
            'Stop charging at',
            'The charger stops at or above this percentage.',
            2,
            100,
        );
        settings.bind('custom-end', endRow, 'value', Gio.SettingsBindFlags.DEFAULT);
        limitsGroup.add(endRow);

        const appearanceGroup = new Adw.PreferencesGroup({title: 'Appearance'});
        page.add(appearanceGroup);

        const iconRow = new Adw.SwitchRow({
            title: 'Show top-panel icon',
            subtitle: 'Show the current Charge Sentinel state beside system indicators.',
        });
        settings.bind('show-panel-icon', iconRow, 'active', Gio.SettingsBindFlags.DEFAULT);
        appearanceGroup.add(iconRow);

        const informationGroup = new Adw.PreferencesGroup({
            title: 'About charge thresholds',
            description: 'Charge Sentinel only enables controls provided by your laptop firmware and Linux battery driver. Desk mode (75% → 80%) is recommended for laptops that spend most of their time connected to power.',
        });
        page.add(informationGroup);
    }
}
