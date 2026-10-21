package com.capstone.mortgage.controller;

import com.capstone.mortgage.entity.Borrower;
import com.capstone.mortgage.entity.Mortgage;
import com.capstone.mortgage.repository.BorrowerRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(BorrowerController.class)
class BorrowerApiTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private BorrowerRepository borrowerRepository;

    @Test
    void createBorrower_ReferenceContract_Returns201() throws Exception {
        when(borrowerRepository.findByBorrowerExternalId("BOR-010")).thenReturn(Optional.empty());
        when(borrowerRepository.save(any(Borrower.class))).thenAnswer(invocation -> {
            Borrower b = invocation.getArgument(0);
            b.setId(UUID.randomUUID());
            return b;
        });

        mockMvc.perform(post("/api/v1/borrowers")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"borrowerExternalId":"BOR-010","firstName":"Alex","lastName":"Rivera",
                                 "email":"alex.rivera@example.test","phone":"+1-555-0100","dateOfBirth":"1988-04-12"}
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.borrowerExternalId").value("BOR-010"))
                .andExpect(jsonPath("$.id").exists());
    }

    @Test
    void getBorrower_WithMortgages_DoesNotSerializeEntityGraph() throws Exception {
        Borrower borrower = new Borrower();
        borrower.setBorrowerExternalId("BOR-001");
        borrower.setFirstName("Jamie");
        Mortgage mortgage = new Mortgage();
        mortgage.setBorrower(borrower);
        borrower.setMortgages(List.of(mortgage));
        when(borrowerRepository.findByBorrowerExternalId("BOR-001")).thenReturn(Optional.of(borrower));

        mockMvc.perform(get("/api/v1/borrowers/BOR-001"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.borrowerExternalId").value("BOR-001"))
                .andExpect(jsonPath("$.mortgages").doesNotExist());
    }

    @Test
    void createBorrower_InvalidId_Returns400() throws Exception {
        mockMvc.perform(post("/api/v1/borrowers")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"borrowerExternalId\":\"B1\",\"firstName\":\"A\",\"lastName\":\"B\",\"email\":\"a@b.test\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"));
    }
}
