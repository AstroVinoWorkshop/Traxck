// NMRA S-9.2.2 Table 1, multi-function decoder CVs (2012.07).
// This is a numbering reference, not a decoder inventory or a table of expected values.
const named = {
  1:'Primary address',2:'Vstart',3:'Acceleration rate',4:'Deceleration rate',5:'Vhigh',6:'Vmid',
  7:'Manufacturer version (read-only)',8:'Manufacturer ID (read-only; writing may reset some decoders)',
  9:'Total PWM period',10:'EMF feedback cutout',11:'Packet time-out',12:'Power source conversion',
  13:'Alternate-mode functions F1–F8',14:'Alternate-mode functions FL, F9–F12',
  15:'Decoder lock (key)',16:'Decoder lock (ID)',17:'Extended address high',18:'Extended address low',
  19:'Consist address',21:'Consist functions F1–F8',22:'Consist functions FL, F9–F12',
  23:'Acceleration adjustment',24:'Deceleration adjustment',25:'Speed table / mid-range step',
  27:'Automatic stopping configuration',28:'Bi-directional communication configuration',
  29:'Configuration data #1',30:'Error information',31:'Index high byte',32:'Index low byte',
  65:'Kick start',66:'Forward trim',95:'Reverse trim',105:'User identifier #1',106:'User identifier #2',
  892:'Decoder load (dynamic)',893:'Dynamic flags (dynamic)',894:'Fuel / coal (dynamic)',895:'Water (dynamic)'
};
export function cvDescription(n){
 if(!Number.isInteger(n)||n<1||n>1024)return null;
 if(named[n])return named[n];
 if(n===20||n===26||n>=96&&n<=104||n>=107&&n<=111||n>=513&&n<=891)return 'Reserved by NMRA for future use';
 if(n>=33&&n<=46)return 'Output location FL/F1–F12 (mapping; decoder-dependent)';
 if(n>=47&&n<=64||n>=112&&n<=256)return 'Manufacturer use (consult decoder manual)';
 if(n>=67&&n<=94)return 'Speed table';
 if(n>=257&&n<=512)return 'Indexed area (CV31/32 select meaning; consult decoder manual)';
 if(n>=896&&n<=1024)return 'SUSI sound/function modules (see NMRA TN-9.2.3)';
 throw Error('Unclassified CV '+n);
}
export const cvReference=Array.from({length:1024},(_,i)=>({number:i+1,description:cvDescription(i+1)}));
export const cvReferenceSource='https://www.nmra.org/sites/default/files/standards/sandrp/DCC/S/s-9.2.2_decoder_cvs_2012.07.pdf';
