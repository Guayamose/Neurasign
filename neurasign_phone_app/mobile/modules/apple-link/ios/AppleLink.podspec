Pod::Spec.new do |s|
  s.name = 'AppleLink'
  s.version = '1.0.0'
  s.summary = 'NEURASIGN HealthKit and paired Apple Watch gateway'
  s.description = s.summary
  s.author = 'NEURASIGN'
  s.homepage = 'https://github.com/Guayamose/Neurasign'
  s.license = { :type => 'MIT' }
  s.platforms = { :ios => '15.1' }
  s.source = { :git => s.homepage }
  s.static_framework = true
  s.dependency 'ExpoModulesCore'
  s.frameworks = 'HealthKit', 'WatchConnectivity'
  s.swift_version = '5.9'
  s.source_files = '**/*.swift'
end
