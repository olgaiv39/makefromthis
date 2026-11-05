export default function ErrorMessage({error}:{error?: Error|string}) {
  if(!error)return null;
  const details=typeof error==='object'&&(error as Error&{details?:string}).details;
  return <div role="alert" className="error"><p>{typeof error==='string'?error:error.message}</p>{details&&<details><summary>Technical details</summary><pre>{details}</pre></details>}</div>;
}
