import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
  Alert,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import MaterialIcons from '@expo/vector-icons/MaterialIcons';
import { useI18n } from '@/contexts/I18nContext';
import type { Language } from '@/i18n/translations';
import * as ImagePicker from 'expo-image-picker';
import { useAuth } from '@/contexts/AuthContext';
import { Avatar } from '@/components/ui/Avatar';
import api from '../../src/api/api';

export default function ClientProfileScreen() {
  const router = useRouter();
  const { user, logout, updateUser } = useAuth();
  const { t } = useI18n();

  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [address, setAddress] = useState('');
  const [aboutMe, setAboutMe] = useState('');
  const [saving, setSaving] = useState(false);

  // Profile photo
  const [selectedPhoto, setSelectedPhoto] = useState<ImagePicker.ImagePickerAsset | null>(null);

  // Password change
  const [showPasswordSection, setShowPasswordSection] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [changingPassword, setChangingPassword] = useState(false);

  useEffect(() => {
    if (user) {
      setFullName(user.full_name || '');
      setEmail(user.email || '');
    }
  }, [user]);

  // Load full profile data from server
  useEffect(() => {
    (async () => {
      try {
        const res = await api.get('/client/profile');
        const data = res.data;
        if (data) {
          setFullName(data.full_name || '');
          setEmail(data.email || '');
          setPhone(data.phone || '');
          setAddress(data.address || '');
          setAboutMe(data.about_me || '');
        }
      } catch (err) {
        console.error('Failed to load profile:', err);
      }
    })();
  }, []);

  const pickProfilePhoto = async () => {
    try {
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        quality: 0.7,
        allowsEditing: true,
        aspect: [1, 1],
      });
      if (!result.canceled && result.assets?.length) {
        setSelectedPhoto(result.assets[0]);
      }
    } catch (err) {
      console.error('Failed to pick photo:', err);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const formData = new FormData();
      formData.append('full_name', fullName);
      formData.append('email', email);
      formData.append('phone', phone);
      formData.append('address', address);
      formData.append('about_me', aboutMe);

      if (selectedPhoto) {
        formData.append('profile_picture', {
          uri: selectedPhoto.uri,
          name: 'profile.jpg',
          type: 'image/jpeg',
        } as any);
      }

      const res = await api.post('/client/profile', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      if (res.data?.success || res.status === 200) {
        Alert.alert(t('success'), t('profileUpdated'));
        // Update local auth context
        if (user) {
          await updateUser({
            ...user,
            full_name: fullName,
            email: email,
            photo: res.data?.photo || user.photo,
          });
        }
        setSelectedPhoto(null);
      }
    } catch (err: any) {
      const msg = err.response?.data?.msg || 'Failed to update profile';
      Alert.alert(t('error'), msg);
    } finally {
      setSaving(false);
    }
  };

  const handleChangePassword = async () => {
    if (!currentPassword || !newPassword) {
      Alert.alert(t('error'), 'Please fill in both password fields');
      return;
    }
    if (newPassword.length < 6) {
      Alert.alert(t('error'), 'New password must be at least 6 characters');
      return;
    }

    setChangingPassword(true);
    try {
      await api.post('/auth/api/change_password', {
        current_password: currentPassword,
        new_password: newPassword,
      });
      Alert.alert(t('success'), 'Password changed successfully');
      setCurrentPassword('');
      setNewPassword('');
      setShowPasswordSection(false);
    } catch (err: any) {
      const msg = err.response?.data?.msg || 'Failed to change password';
      Alert.alert(t('error'), msg);
    } finally {
      setChangingPassword(false);
    }
  };

  const handleDeleteAccount = () => {
    Alert.alert(t('deleteAccount'), t('deleteAccountConfirm'), [
      { text: t('cancel'), style: 'cancel' },
      {
        text: t('deleteAccount'),
        style: 'destructive',
        onPress: async () => {
          try {
            await api.post('/auth/delete_account');
            logout();
          } catch (err: any) {
            const msg = err.response?.data?.msg || 'Failed to delete account';
            Alert.alert(t('error'), msg);
          }
        },
      },
    ]);
  };

  const handleLogout = () => {
    Alert.alert(t('logout'), t('logoutConfirm'), [
      { text: t('cancel'), style: 'cancel' },
      {
        text: t('logout'),
        style: 'destructive',
        onPress: () => logout(),
      },
    ]);
  };

  const avatarDisplayUri = selectedPhoto
    ? selectedPhoto.uri
    : user?.photo
      ? `https://human-me.com/static/uploads/${user.photo}`
      : null;

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView contentContainerStyle={styles.scrollContent} keyboardShouldPersistTaps="handled">
          <Text style={styles.title}>{t('myProfile')}</Text>

          {/* Avatar */}
          <View style={styles.avatarSection}>
            <TouchableOpacity activeOpacity={0.7} onPress={pickProfilePhoto}>
              <Avatar uri={avatarDisplayUri} name={fullName || user?.username} size={90} />
              <View style={styles.avatarEditBadge}>
                <MaterialIcons name="camera-alt" size={16} color="#fff" />
              </View>
            </TouchableOpacity>
          </View>

          {/* Form Fields */}
          <View style={styles.formSection}>
            <Text style={styles.label}>{t('fullName')}</Text>
            <TextInput
              style={styles.input}
              value={fullName}
              onChangeText={setFullName}
              placeholder="Your full name"
              placeholderTextColor="#9ca3af"
              autoCapitalize="words"
            />

            <Text style={styles.label}>{t('email')}</Text>
            <TextInput
              style={styles.input}
              value={email}
              onChangeText={setEmail}
              placeholder="your@email.com"
              placeholderTextColor="#9ca3af"
              keyboardType="email-address"
              autoCapitalize="none"
            />

            <Text style={styles.label}>{t('phone')}</Text>
            <TextInput
              style={styles.input}
              value={phone}
              onChangeText={setPhone}
              placeholder="+1 234 567 890"
              placeholderTextColor="#9ca3af"
              keyboardType="phone-pad"
            />

            <Text style={styles.label}>{t('address')}</Text>
            <TextInput
              style={styles.input}
              value={address}
              onChangeText={setAddress}
              placeholder="Your address"
              placeholderTextColor="#9ca3af"
            />

            <Text style={styles.label}>{t('aboutMe')}</Text>
            <TextInput
              style={[styles.input, styles.textArea]}
              value={aboutMe}
              onChangeText={setAboutMe}
              placeholder="Tell us about yourself..."
              placeholderTextColor="#9ca3af"
              multiline
              numberOfLines={4}
              textAlignVertical="top"
            />
          </View>

          {/* Save Button */}
          <TouchableOpacity
            style={styles.saveBtn}
            onPress={handleSave}
            disabled={saving}
            activeOpacity={0.7}
          >
            {saving ? (
              <ActivityIndicator color="#fff" size="small" />
            ) : (
              <Text style={styles.saveBtnText}>{t('save')}</Text>
            )}
          </TouchableOpacity>

          {/* Change Password Collapsible */}
          <TouchableOpacity
            style={styles.collapsibleHeader}
            onPress={() => setShowPasswordSection(!showPasswordSection)}
            activeOpacity={0.7}
          >
            <Text style={styles.collapsibleTitle}>{t('changePassword')}</Text>
            <MaterialIcons
              name={showPasswordSection ? 'expand-less' : 'expand-more'}
              size={24}
              color="#374151"
            />
          </TouchableOpacity>

          {showPasswordSection && (
            <View style={styles.passwordSection}>
              <Text style={styles.label}>{t('currentPassword')}</Text>
              <TextInput
                style={styles.input}
                value={currentPassword}
                onChangeText={setCurrentPassword}
                placeholder="Enter current password"
                placeholderTextColor="#9ca3af"
                secureTextEntry
              />

              <Text style={styles.label}>{t('newPassword')}</Text>
              <TextInput
                style={styles.input}
                value={newPassword}
                onChangeText={setNewPassword}
                placeholder="Enter new password"
                placeholderTextColor="#9ca3af"
                secureTextEntry
              />

              <TouchableOpacity
                style={styles.changePasswordBtn}
                onPress={handleChangePassword}
                disabled={changingPassword}
                activeOpacity={0.7}
              >
                {changingPassword ? (
                  <ActivityIndicator color="#fff" size="small" />
                ) : (
                  <Text style={styles.changePasswordBtnText}>{t('updatePassword')}</Text>
                )}
              </TouchableOpacity>
            </View>
          )}

          {/* Quick Links */}
          <View style={styles.linksSection}>
            <TouchableOpacity
              style={styles.linkRow}
              onPress={() => router.push('/service-history' as any)}
              activeOpacity={0.7}
            >
              <MaterialIcons name="history" size={22} color="#3f4a36" />
              <Text style={styles.linkText}>{t('serviceHistory')}</Text>
              <MaterialIcons name="chevron-right" size={22} color="#9ca3af" />
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.linkRow}
              onPress={() => router.push('/feedback' as any)}
              activeOpacity={0.7}
            >
              <MaterialIcons name="feedback" size={22} color="#3f4a36" />
              <Text style={styles.linkText}>{t('feedback')}</Text>
              <MaterialIcons name="chevron-right" size={22} color="#9ca3af" />
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.linkRow}
              onPress={() => router.push('/documents' as any)}
              activeOpacity={0.7}
            >
              <MaterialIcons name="description" size={22} color="#3f4a36" />
              <Text style={styles.linkText}>{t('documents')}</Text>
              <MaterialIcons name="chevron-right" size={22} color="#9ca3af" />
            </TouchableOpacity>
          </View>

          {/* Language */}
          <LanguageSelector />

          {/* Logout */}
          <TouchableOpacity
            style={styles.logoutBtn}
            onPress={handleLogout}
            activeOpacity={0.7}
          >
            <MaterialIcons name="logout" size={20} color="#ef4444" />
            <Text style={styles.logoutBtnText}>{t('logout')}</Text>
          </TouchableOpacity>

          {/* Delete Account */}
          <TouchableOpacity style={styles.deleteAccountBtn} onPress={handleDeleteAccount}>
            <Text style={styles.deleteAccountBtnText}>{t('deleteAccount')}</Text>
          </TouchableOpacity>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const LANGS: { code: Language; label: string }[] = [
  { code: 'en', label: 'EN' },
  { code: 'uk', label: 'UK' },
  { code: 'de', label: 'DE' },
  { code: 'pl', label: 'PL' },
];

function LanguageSelector() {
  const { language, setLanguage, t } = useI18n();
  return (
    <View style={{ marginTop: 20, marginBottom: 10 }}>
      <Text style={{ fontSize: 16, fontWeight: '600', color: '#333', marginBottom: 10 }}>
        {t('language')}
      </Text>
      <View style={{ flexDirection: 'row', gap: 10 }}>
        {LANGS.map(l => (
          <TouchableOpacity
            key={l.code}
            onPress={() => setLanguage(l.code)}
            style={{
              paddingHorizontal: 16, paddingVertical: 8, borderRadius: 20,
              backgroundColor: language === l.code ? '#3f4a36' : '#f3f4f6',
              borderWidth: 1, borderColor: language === l.code ? '#3f4a36' : '#e5e7eb',
            }}
          >
            <Text style={{
              fontWeight: '600', fontSize: 14,
              color: language === l.code ? '#fff' : '#333',
            }}>{l.label}</Text>
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f9fafb',
  },
  scrollContent: {
    paddingHorizontal: 20,
    paddingBottom: 40,
  },
  title: {
    fontSize: 22,
    fontWeight: '700',
    color: '#3f4a36',
    marginTop: 8,
    marginBottom: 20,
  },
  avatarSection: {
    alignItems: 'center',
    marginBottom: 24,
  },
  avatarEditBadge: {
    position: 'absolute',
    bottom: 0,
    right: 0,
    backgroundColor: '#3f4a36',
    width: 28,
    height: 28,
    borderRadius: 14,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 2,
    borderColor: '#fff',
  },
  formSection: {
    gap: 4,
  },
  label: {
    fontSize: 14,
    fontWeight: '600',
    color: '#374151',
    marginBottom: 6,
    marginTop: 12,
  },
  input: {
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#d1d5db',
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 16,
    color: '#1f2937',
  },
  textArea: {
    minHeight: 100,
    paddingTop: 12,
  },
  saveBtn: {
    backgroundColor: '#3f4a36',
    paddingVertical: 14,
    borderRadius: 10,
    alignItems: 'center',
    marginTop: 24,
  },
  saveBtnText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  collapsibleHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 16,
    marginTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#e5e7eb',
  },
  collapsibleTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#374151',
  },
  passwordSection: {
    marginBottom: 8,
  },
  changePasswordBtn: {
    backgroundColor: '#3f4a36',
    paddingVertical: 12,
    borderRadius: 10,
    alignItems: 'center',
    marginTop: 16,
  },
  changePasswordBtnText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '600',
  },
  linksSection: {
    marginTop: 20,
    gap: 2,
  },
  linkRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: '#e5e7eb',
    gap: 12,
  },
  linkText: {
    flex: 1,
    fontSize: 16,
    fontWeight: '500',
    color: '#1f2937',
  },
  logoutBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    paddingVertical: 14,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#ef4444',
    marginTop: 20,
  },
  logoutBtnText: {
    color: '#ef4444',
    fontSize: 16,
    fontWeight: '600',
  },
  deleteAccountBtn: {
    backgroundColor: '#fef2f2',
    borderColor: '#ef4444',
    borderWidth: 1.5,
    padding: 16,
    borderRadius: 10,
    alignItems: 'center',
    marginTop: 12,
  },
  deleteAccountBtnText: {
    color: '#ef4444',
    fontSize: 16,
    fontWeight: '600',
  },
});
