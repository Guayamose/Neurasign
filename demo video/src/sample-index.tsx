// Archived first experiment, kept separate from the full hospital film.
import React from 'react';
import {Composition,registerRoot} from 'remotion';
import {NeurasignSample} from './Sample';
registerRoot(()=> <Composition id="NeurasignSample" component={NeurasignSample} durationInFrames={450} fps={30} width={1920} height={1080}/>);
