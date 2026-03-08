import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import MaterialIcons from '@expo/vector-icons/MaterialIcons';
import * as ImagePicker from 'expo-image-picker';
import { useAuth } from '@/contexts/AuthContext';
import { useI18n } from '@/contexts/I18nContext';
import type { Language } from '@/i18n/translations';
import { Avatar } from '@/components/ui/Avatar';
import { Card } from '@/components/ui/Card';
import api from '../../src/api/api';

export default function ProviderProfileScreen() {
  const router = useRouter();
  const { user, logout, updateUser } = useAuth();
  const { t } = useI18n();

  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [address, setAddress] = useState('');
  const [aboutMe, setAboutMe] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [selectedPhoto, setSelectedPhoto] = useState<ImagePicker.ImagePickerAsset | null>(null);

  // Password change
  const [showPasswordSection, setShowPasswordSection] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [changingPassword, setChangingPassword] = useState(false);

  useEffect(() => {
    loadProfile();
  }, []);

  const loadProfile = async () => {
    setLoading(true);
    try {
      const res = await api.get('/provider/profile');
      const data = res.data;
      setFullName(data.full_name || '');
      setEmail(data.email || '');
      setPhone(data.phone || '');
      setAddress(data.address || '');
      setAboutMe(data.about_me || '');
    } catch (err) {
      // Fallback to local user data
      setFullName(user?.full_name || '');
      setEmail(user?.email || '');
    } finally {
      setLoading(false);
    }
  };

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

      const res = await api.post('/provider/profile', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      // Update local user state
      if (user) {
        await updateUser({ ...user, full_name: fullName, email, photo: res.data?.photo || user.photo });
      }

      setSelectedPhoto(null);
      Alert.alert(t('success'), t('profileUpdated'));
    } catch (err: any) {
      const msg = err.response?.data?.msg || t('error');
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

  if (loading) {
    return (
      <SafeAreaView style={styles.centered}>
        <ActivityIndicator size="large" color="#3f4a36" />
      </SafeAreaView>
    );
  }

  const avatarDisplayUri = selectedPhoto
    ? selectedPhoto.uri
    : user?.photo
      ? `https://human-me.com${user.photo}`
      : null;

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={{ flex: 1 }}
      >
        <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
          <Text style={styles.screenTitle}>{t('myProfile')}</Text>

          <View style={styles.avatarSection}>
            <TouchableOpacity activeOpacity={0.7} onPress={pickProfilePhoto}>
              <Avatar uri={avatarDisplayUri} name={fullName || user?.username} size={90} />
              <View style={styles.avatarEditBadge}>
                <MaterialIcons name="camera-alt" size={16} color="#fff" />
              </View>
            </TouchableOpacity>
            <Text style={styles.username}>@{user?.username}</Text>
          </View>

          <View style={styles.form}>
            <Text style={styles.label}>{t('fullName')}</Text>
            <TextInput
              style={styles.input}
              value={fullName}
              onChangeText={setFullName}
              placeholder={t('fullName')}
            />

            <Text style={styles.label}>{t('email')}</Text>
            <TextInput
              style={styles.input}
              value={email}
              onChangeText={setEmail}
              placeholder={t('email')}
              keyboardType="email-address"
              autoCapitalize="none"
            />

            <Text style={styles.label}>{t('phone')}</Text>
            <TextInput
              style={styles.input}
              value={phone}
              onChangeText={setPhone}
              placeholder={t('phone')}
              keyboardType="phone-pad"
            />

            <Text style={styles.label}>{t('address')}</Text>
            <TextInput
              style={styles.input}
              value={address}
              onChangeText={setAddress}
              placeholder={t('address')}
            />

            <Text style={styles.label}>{t('aboutMe')}</Text>
            <TextInput
              style={[styles.input, styles.textArea]}
              value={aboutMe}
              onChangeText={setAboutMe}
              placeholder={t('aboutMe')}
              multiline
              numberOfLines={4}
              textAlignVertical="top"
            />

            {saving ? (
              <ActivityIndicator size="large" color="#3f4a36" style={{ marginVertical: 20 }} />
            ) : (
              <TouchableOpacity style={styles.saveBtn} onPress={handleSave}>
                <Text style={styles.saveBtnText}>{t('save')}</Text>
              </TouchableOpacity>
            )}

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
                  secureTextEntry
                />

                <Text style={styles.label}>{t('newPassword')}</Text>
                <TextInput
                  style={styles.input}
                  value={newPassword}
                  onChangeText={setNewPassword}
                  placeholder="Enter new password"
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
              <Card
                style={styles.linkCard}
                onPress={() => router.push('/provider-services' as any)}
              >
                <View style={styles.linkRow}>
                  <View style={styles.linkIconContainer}>
                    <Text style={styles.linkIcon}>{'\u2699'}</Text>
                  </View>
                  <View style={styles.linkInfo}>
                    <Text style={styles.linkTitle}>{t('myServices')}</Text>
                    <Text style={styles.linkSubtitle}>{t('manageServices')}</Text>
                  </View>
                  <Text style={styles.linkArrow}>{'\u203A'}</Text>
                </View>
              </Card>

              <Card
                style={styles.linkCard}
                onPress={() => router.push('/portfolio' as any)}
              >
                <View style={styles.linkRow}>
                  <View style={styles.linkIconContainer}>
                    <Text style={styles.linkIcon}>{'\u{1F4F7}'}</Text>
                  </View>
                  <View style={styles.linkInfo}>
                    <Text style={styles.linkTitle}>{t('portfolio')}</Text>
                    <Text style={styles.linkSubtitle}>{t('showcaseWork')}</Text>
                  </View>
                  <Text style={styles.linkArrow}>{'\u203A'}</Text>
                </View>
              </Card>

              <Card
                style={styles.linkCard}
                onPress={() => router.push('/documents' as any)}
              >
                <View style={styles.linkRow}>
                  <View style={styles.linkIconContainer}>
                    <Text style={styles.linkIcon}>{'\u{1F4C4}'}</Text>
                  </View>
                  <View style={styles.linkInfo}>
                    <Text style={styles.linkTitle}>{t('documents')}</Text>
                    <Text style={styles.linkSubtitle}>{t('uploadDocument')}</Text>
                  </View>
                  <Text style={styles.linkArrow}>{'\u203A'}</Text>
                </View>
              </Card>

              <Card
                style={styles.linkCard}
                onPress={() => router.push('/cancellation-policy' as any)}
              >
                <View style={styles.linkRow}>
                  <View style={styles.linkIconContainer}>
                    <Text style={styles.linkIcon}>{'\u{1F6E1}'}</Text>
                  </View>
                  <View style={styles.linkInfo}>
                    <Text style={styles.linkTitle}>{t('setCancellationPolicy')}</Text>
                    <Text style={styles.linkSubtitle}>{t('cancellationPolicy')}</Text>
                  </View>
                  <Text style={styles.linkArrow}>{'\u203A'}</Text>
                </View>
              </Card>

              <Card
                style={styles.linkCard}
                onPress={() => router.push('/service-history' as any)}
              >
                <View style={styles.linkRow}>
                  <View style={styles.linkIconContainer}>
                    <Text style={styles.linkIcon}>{'\u{1F4CB}'}</Text>
                  </View>
                  <View style={styles.linkInfo}>
                    <Text style={styles.linkTitle}>{t('serviceHistory')}</Text>
                    <Text style={styles.linkSubtitle}>{t('noHistory')}</Text>
                  </View>
                  <Text style={styles.linkArrow}>{'\u203A'}</Text>
                </View>
              </Card>

              <Card
                style={styles.linkCard}
                onPress={() => router.push('/finances' as any)}
              >
                <View style={styles.linkRow}>
                  <View style={styles.linkIconContainer}>
                    <Text style={styles.linkIcon}>{'\u{1F4B3}'}</Text>
                  </View>
                  <View style={styles.linkInfo}>
                    <Text style={styles.linkTitle}>{t('finances')}</Text>
                    <Text style={styles.linkSubtitle}>{t('stripeEarnings')}</Text>
                  </View>
                  <Text style={styles.linkArrow}>{'\u203A'}</Text>
                </View>
              </Card>
            </View>

            {/* Language */}
            <LanguageSelector />

            <TouchableOpacity style={styles.logoutBtn} onPress={handleLogout}>
              <Text style={styles.logoutBtnText}>{t('logout')}</Text>
            </TouchableOpacity>

            <TouchableOpacity style={styles.deleteAccountBtn} onPress={handleDeleteAccount}>
              <Text style={styles.deleteAccountBtnText}>{t('deleteAccount')}</Text>
            </TouchableOpacity>
          </View>
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
  centered: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#f9fafb',
  },
  scrollContent: {
    paddingHorizontal: 20,
    paddingBottom: 40,
  },
  screenTitle: {
    fontSize: 22,
    fontWeight: '700',
    color: '#3f4a36',
    paddingTop: 8,
    paddingBottom: 16,
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
  username: {
    fontSize: 14,
    color: '#6b7280',
    marginTop: 8,
  },
  form: {
    width: '100%',
  },
  label: {
    marginBottom: 8,
    color: '#333',
    fontWeight: '600',
    fontSize: 14,
  },
  input: {
    height: 50,
    borderColor: '#e1e1e1',
    borderWidth: 1,
    marginBottom: 16,
    paddingHorizontal: 15,
    borderRadius: 10,
    backgroundColor: '#fff',
    fontSize: 16,
  },
  textArea: {
    height: 100,
    paddingTop: 12,
  },
  saveBtn: {
    backgroundColor: '#3f4a36',
    padding: 16,
    borderRadius: 10,
    alignItems: 'center',
    marginTop: 8,
  },
  saveBtnText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: 'bold',
  },
  linksSection: {
    marginTop: 24,
    marginBottom: 8,
    gap: 10,
  },
  linkCard: {
    paddingVertical: 4,
    paddingHorizontal: 4,
  },
  linkRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  linkIconContainer: {
    width: 42,
    height: 42,
    borderRadius: 10,
    backgroundColor: '#f0f1ee',
    justifyContent: 'center',
    alignItems: 'center',
  },
  linkIcon: {
    fontSize: 20,
  },
  linkInfo: {
    flex: 1,
  },
  linkTitle: {
    fontSize: 15,
    fontWeight: '600',
    color: '#1f2937',
  },
  linkSubtitle: {
    fontSize: 13,
    color: '#6b7280',
    marginTop: 1,
  },
  linkArrow: {
    fontSize: 24,
    color: '#9ca3af',
    fontWeight: '300',
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
  logoutBtn: {
    borderColor: '#ef4444',
    borderWidth: 1.5,
    padding: 16,
    borderRadius: 10,
    alignItems: 'center',
    marginTop: 16,
  },
  logoutBtnText: {
    color: '#ef4444',
    fontSize: 18,
    fontWeight: 'bold',
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
