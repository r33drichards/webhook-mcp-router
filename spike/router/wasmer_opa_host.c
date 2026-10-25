/* Local synthetic probe: native C host, OPA policy executed by Wasmer.
 * No WASI, network, filesystem or custom builtin imports are exposed to policy.
 * Not a Go guest integration or production general-purpose ABI implementation.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "wasm.h"
static wasm_exporttype_vec_t types;
static wasm_extern_vec_t exports;
static void fail(const char *msg) { fprintf(stderr,"%s\n",msg); exit(1); }
static wasm_trap_t *deny(const wasm_val_vec_t *args, wasm_val_vec_t *results) {
 (void)args; (void)results; fail("OPA host builtin/abort invoked: denied"); return NULL;
}
static int nameeq(const wasm_name_t *n,const char *s) {return n->size==strlen(s)&&memcmp(n->data,s,n->size)==0;}
static wasm_func_t *fn(const char *name) {
 for(size_t i=0;i<types.size;i++) if(nameeq(wasm_exporttype_name(types.data[i]),name)) return wasm_extern_as_func(exports.data[i]);
 fail("missing export"); return NULL;
}
static int32_t call(const char *name,int n,int32_t a,int32_t b,int out) {
 wasm_val_t av[2]={{.kind=WASM_I32,.of.i32=a},{.kind=WASM_I32,.of.i32=b}};
 wasm_val_t rv[1]={{.kind=WASM_I32}};
 wasm_val_vec_t args={(size_t)n,av},results={(size_t)out,rv};
 wasm_trap_t *t=wasm_func_call(fn(name),&args,&results);
 if(t) {wasm_message_t msg;wasm_trap_message(t,&msg);fprintf(stderr,"trap: %.*s\n",(int)msg.size,msg.data);exit(1);}
 return out?rv[0].of.i32:0;
}
static char *str(wasm_memory_t *mem,int32_t ptr) {
 size_t size=wasm_memory_data_size(mem);
 if(ptr<0||(size_t)ptr>=size)fail("bad pointer");
 char *p=(char*)wasm_memory_data(mem)+ptr;
 if(!memchr(p,0,size-ptr))fail("unterminated JSON");
 return p;
}
int main(int argc,char **argv) {
 if(argc!=2)fail("usage: wasmer-opa-host policy.wasm < input.json");
 FILE *f=fopen(argv[1],"rb");if(!f)fail("open module");
 fseek(f,0,SEEK_END);long len=ftell(f);rewind(f);
 if(len<0||len>1024*1024)fail("module size");
 wasm_byte_vec_t bytes;wasm_byte_vec_new_uninitialized(&bytes,len);
 if(fread(bytes.data,1,len,f)!=(size_t)len)fail("read module");
 fclose(f);
 wasm_engine_t *engine=wasm_engine_new();wasm_store_t *store=wasm_store_new(engine);
 wasm_module_t *module=wasm_module_new(store,&bytes);if(!module)fail("compile module");
 wasm_importtype_vec_t imports;wasm_module_imports(module,&imports);
 wasm_extern_vec_t values;wasm_extern_vec_new_uninitialized(&values,imports.size);
 wasm_memory_t *memory=NULL;
 for(size_t i=0;i<imports.size;i++) {
  const wasm_externtype_t *t=wasm_importtype_type(imports.data[i]);
  if(!nameeq(wasm_importtype_module(imports.data[i]),"env"))fail("unexpected import module");
  if(wasm_externtype_kind(t)==WASM_EXTERN_MEMORY) {
   if(!nameeq(wasm_importtype_name(imports.data[i]),"memory"))fail("unexpected memory");
   wasm_limits_t limits={2,128}; /* 8 MiB upper bound */
   wasm_memorytype_t *mt=wasm_memorytype_new(&limits);
   memory=wasm_memory_new(store,mt);values.data[i]=wasm_memory_as_extern(memory);
  } else if(wasm_externtype_kind(t)==WASM_EXTERN_FUNC) {
   const wasm_name_t *nm=wasm_importtype_name(imports.data[i]);
   if(!nameeq(nm,"opa_abort") && !(nm->size==12 && memcmp(nm->data,"opa_builtin",11)==0 && nm->data[11]>='0' && nm->data[11]<='4'))fail("unexpected import function");
   wasm_func_t *fun=wasm_func_new(store,wasm_externtype_as_functype_const(t),deny);values.data[i]=wasm_func_as_extern(fun);
  } else fail("unexpected import kind");
 }
 wasm_trap_t *trap=NULL;wasm_instance_t *instance=wasm_instance_new(store,module,&values,&trap);
 if(!instance)fail("instantiate module");
 wasm_module_exports(module,&types);wasm_instance_exports(instance,&exports);
 if(strcmp(str(memory,call("opa_json_dump",1,call("builtins",0,0,0,1),0,1)),"{}"))fail("policy requires host builtins");
 char raw[65537];size_t size=fread(raw,1,sizeof(raw),stdin);if(size>65536)fail("input limit");
 int32_t ptr=call("opa_malloc",1,size,0,1);
 if(ptr<0||(size_t)ptr+size>wasm_memory_data_size(memory))fail("input memory range");
 memcpy(wasm_memory_data(memory)+ptr,raw,size);
 int32_t input=call("opa_json_parse",2,ptr,size,1);if(!input)fail("invalid JSON");
 int32_t ctx=call("opa_eval_ctx_new",0,0,0,1);
 call("opa_eval_ctx_set_input",2,ctx,input,0);
 call("opa_eval_ctx_set_entrypoint",2,ctx,0,0);
 call("eval",1,ctx,0,1);
 int32_t result=call("opa_eval_ctx_get_result",1,ctx,0,1);
 puts(str(memory,call("opa_json_dump",1,result,0,1)));
 return 0;
}
