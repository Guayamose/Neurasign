import React from 'react';
import {Composition} from 'remotion';
import {HospitalFilm} from './hospital/HospitalFilm';

export const VideoRoot: React.FC = () => <>
<Composition id="NeurasignHospital" component={HospitalFilm} durationInFrames={2280} fps={30} width={3840} height={2160} defaultProps={{audio:true}}/>
<Composition id="NeurasignHospital1080" component={HospitalFilm} durationInFrames={2280} fps={30} width={1920} height={1080} defaultProps={{audio:true}}/>
</>;
