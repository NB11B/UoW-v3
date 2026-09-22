idf_component_register(
    SRCS "../src/main.cpp" "../src/uow_embedded.cpp"
    INCLUDE_DIRS "../include"
    REQUIRES driver esp_driver_usb_serial_jtag
)

if(NOT DEFINED UOW_PROPOSER_CORE)
    set(UOW_PROPOSER_CORE 0)
endif()
if(NOT DEFINED UOW_AUTHORITY_CORE)
    set(UOW_AUTHORITY_CORE 1)
endif()

target_compile_options(${COMPONENT_LIB} PRIVATE -std=gnu++17 -fexceptions)
target_compile_definitions(${COMPONENT_LIB} PRIVATE
    UOW_PROPOSER_CORE=${UOW_PROPOSER_CORE}
    UOW_AUTHORITY_CORE=${UOW_AUTHORITY_CORE}
)

