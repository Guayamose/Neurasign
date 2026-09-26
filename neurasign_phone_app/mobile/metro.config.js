const { getDefaultConfig } = require('expo/metro-config');
const path = require('path');
const config = getDefaultConfig(__dirname);
config.watchFolders = ['src', 'contracts'].map(folder => path.resolve(__dirname, '..', folder));
config.resolver.resolveRequest = (context, moduleName, platform) => {
  if (context.originModulePath.startsWith(path.resolve(__dirname, '..', 'src')) && moduleName.endsWith('.js')) moduleName = moduleName.slice(0, -3);
  return context.resolveRequest(context, moduleName, platform);
};
module.exports = config;
