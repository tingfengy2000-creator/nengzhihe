import path from 'node:path';
import {pathToFileURL} from 'node:url';
const R=path.resolve(import.meta.dirname,'../..');
const home=process.env.USERPROFILE;
const skill=path.join(home,'.codex/plugins/cache/openai-primary-runtime/presentations/26.921.10847/skills/presentations');
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const result=await finalizePresentation({workspaceDir:path.join(R,'presentation'),candidatePath:path.join(R,'presentation/working/candidate.pptx'),finalPath:path.join(R,'presentation/final/能智核_实际核查任务答辩.pptx'),pythonExecutable:path.join(home,'.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'),integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),explicitTotalSlideCount:10,layoutArgs:['--cover-role','cover','--expected-aspect','16:9','--expected-slide-size-emu','12192000,6858000','--require-native-table-slide','6','--require-native-table-slide','7','--validate-heading-fit'],requiredNativeTableOwnerSlides:[6,7],fontPolicy:{basis:'design',families:['Microsoft YaHei']},verifyArtifactToolImport:true,receiptPath:path.join(R,'presentation/working/final_validation_v2.json')});
console.log(JSON.stringify({finalPath:result.finalPath,receiptPath:result.receiptPath}));
